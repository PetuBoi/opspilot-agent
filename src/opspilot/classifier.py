"""Reproducible TF-IDF baselines with training-only model selection."""

import hashlib
import json
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from opspilot.datasets import load
from opspilot.demo import TOPICS
from opspilot.domain import Prediction

SEED = 42


def preprocess(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).lower()).strip()


def frames(dataset: str, external: Path = Path("data/external/it-support")):
    if dataset == "it-support":
        return load(external)
    if dataset != "demo":
        raise ValueError("Supported datasets: demo, it-support")
    train, test = [], []
    for service, symptom, checks, _ in TOPICS:
        for prefix in (
            "Please investigate",
            "Employee reports",
            "Unable to work because",
            "Help with",
        ):
            train.append({"text": f"{prefix}: {symptom}. {checks}", "label": service})
        test.append(
            {"text": f"New request: {symptom} affecting workstation today", "label": service}
        )
    return pd.DataFrame(train), pd.DataFrame(test), {"origin": "SYNTHETIC", "revision": "demo-v1"}


def train_classifier(
    dataset: str,
    artifact_dir: Path,
    report_dir: Path,
    external: Path = Path("data/external/it-support"),
) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    train, test, provenance = frames(dataset, external)
    train, test = train.copy(), test.copy()
    evaluation_labels = sorted(set(train.label) | set(test.label))
    # Text identity only: quarantine published contamination without consulting test labels.
    train["identity"] = train.text.map(preprocess)
    test_identity = set(test.text.map(preprocess))
    overlap = train.identity.isin(test_identity)
    excluded = int(overlap.sum())
    train = train.loc[~overlap].reset_index(drop=True)
    split = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    fit_idx, valid_idx = next(split.split(train, groups=train.identity))
    if train.iloc[fit_idx].label.nunique() != train.label.nunique():
        raise ValueError("Training group split omitted a category; need more independent records")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    comparisons, validation = [], []
    pipelines = {}
    for name, estimator in (
        ("logistic_regression", LogisticRegression(max_iter=2000, random_state=SEED)),
        ("linear_svc", LinearSVC(random_state=SEED, max_iter=5000)),
    ):
        best_score, best_pipeline, best_c = -1.0, None, 0.0
        for c in (0.5, 2.0):
            estimator.set_params(C=c)
            pipeline = Pipeline(
                [
                    (
                        "tfidf",
                        TfidfVectorizer(
                            preprocessor=preprocess,
                            ngram_range=(1, 2),
                            sublinear_tf=True,
                            max_features=20000,
                        ),
                    ),
                    ("classifier", sklearn.base.clone(estimator)),
                ]
            )
            pipeline.fit(train.iloc[fit_idx].text, train.iloc[fit_idx].label)
            score = f1_score(
                train.iloc[valid_idx].label,
                pipeline.predict(train.iloc[valid_idx].text),
                average="macro",
                zero_division=0,
            )
            validation.append({"model": name, "C": c, "validation_macro_f1": score})
            if score > best_score:
                best_score, best_pipeline, best_c = score, pipeline, c
        best_pipeline.fit(train.text, train.label)
        start = time.perf_counter()
        predicted = best_pipeline.predict(test.text)
        latency = (time.perf_counter() - start) * 1000 / len(test)
        report = classification_report(
            test.label, predicted, labels=evaluation_labels, output_dict=True, zero_division=0
        )
        metrics = {
            "model": name,
            "C": best_c,
            "validation_macro_f1": best_score,
            "accuracy": accuracy_score(test.label, predicted),
            "macro_f1": f1_score(test.label, predicted, average="macro", zero_division=0),
            "weighted_f1": f1_score(test.label, predicted, average="weighted", zero_division=0),
            "mean_batch_inference_ms_per_ticket": latency,
        }
        comparisons.append(metrics)
        pipelines[name] = best_pipeline
        (report_dir / f"{name}_report.json").write_text(json.dumps(report, indent=2), "utf-8")
        # Keep categories absent from decontaminated training visible in evaluation.
        labels = evaluation_labels
        fig, ax = plt.subplots(figsize=(9, 7))
        matrix = confusion_matrix(test.label, predicted, labels=labels)
        pd.DataFrame(matrix, index=labels, columns=labels).to_csv(
            report_dir / f"{name}_confusion_matrix.csv", index_label="actual"
        )
        ax.imshow(matrix, cmap="Blues")
        for (i, j), count in np.ndenumerate(matrix):
            ax.text(j, i, str(count), ha="center", va="center")
        ax.set(
            xticks=range(len(labels)),
            yticks=range(len(labels)),
            xticklabels=labels,
            yticklabels=labels,
            xlabel="Predicted",
            ylabel="Actual",
            title=f"{dataset}: {name} (original held-out test)",
        )
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        fig.tight_layout()
        fig.savefig(report_dir / f"{name}_confusion_matrix.png")
        plt.close(fig)
    # Never select the production model on the held-out test result.
    selected = max(comparisons, key=lambda row: row["validation_macro_f1"])["model"]
    metadata = {
        "dataset": dataset,
        "provenance": provenance,
        "seed": SEED,
        "sklearn_version": sklearn.__version__,
        "trained_at": datetime.now(UTC).isoformat(),
        "selected_model": selected,
        "selection": "training-only grouped validation macro-F1",
        "train_rows": len(train),
        "validation_rows": len(valid_idx),
        "test_rows": len(test),
        "quarantined_train_rows": excluded,
        "evaluation_labels": evaluation_labels,
        "trained_labels": sorted(train.label.unique().tolist()),
        "labels_without_training_examples": sorted(set(evaluation_labels) - set(train.label)),
        "split": "Original test; normalized overlap quarantined; grouped training validation",
        "training_digest": hashlib.sha256("\n".join(sorted(train.identity)).encode()).hexdigest(),
        "features": "NFKC lowercase word TF-IDF, 1-2 grams, 20k max, sublinear TF",
        "validation_search": validation,
        "comparison": comparisons,
        "limitations": "Exact duplicates controlled; semantic near duplicates may remain",
    }
    joblib.dump(
        {"pipeline": pipelines[selected], "metadata": metadata}, artifact_dir / "classifier.joblib"
    )
    (artifact_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), "utf-8")
    (report_dir / "classification_summary.json").write_text(json.dumps(metadata, indent=2), "utf-8")
    pd.DataFrame(comparisons).to_csv(report_dir / "model_comparison.csv", index=False)
    rows = [
        "# Classification evaluation",
        "",
        f"Dataset: {dataset}. Selection: validation only.",
        "",
        "| Model | Accuracy | Macro-F1 | Weighted-F1 |",
        "|---|---:|---:|---:|",
    ]
    rows.extend(
        f"| {r['model']} | {r['accuracy']:.4f} | {r['macro_f1']:.4f} | {r['weighted_f1']:.4f} |"
        for r in comparisons
    )
    rows.extend(
        [
            "",
            f"Quarantined {excluded} overlapping training rows. Test rows: {len(test)}.",
            "Classification only; these metrics do not measure incident resolution quality.",
        ]
    )
    rows.append(
        "Categories with no clean training examples: "
        + (", ".join(metadata["labels_without_training_examples"]) or "none")
        + ". All original categories remain in held-out metrics and confusion matrices."
    )
    (report_dir / "classification_report.md").write_text("\n".join(rows) + "\n", "utf-8")
    return metadata


class Classifier:
    def __init__(self, artifact_dir: Path):
        path = artifact_dir / "classifier.joblib"
        if not path.is_file():
            raise ValueError("Classifier missing; run seed-demo or train-classifier first")
        # Only local application-created artifacts are trusted. joblib can execute code.
        saved = joblib.load(path)
        self.pipeline, self.metadata = saved["pipeline"], saved["metadata"]

    def predict(self, text: str) -> Prediction:
        label = str(self.pipeline.predict([text])[0])
        probability = None
        if hasattr(self.pipeline, "predict_proba"):
            probability = float(self.pipeline.predict_proba([text]).max())
        return Prediction(
            label=label,
            model=self.metadata["selected_model"],
            dataset=self.metadata["dataset"],
            probability=probability,
        )
