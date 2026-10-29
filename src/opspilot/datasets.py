"""Pinned, cached acquisition and honest EDA of the authentic classification dataset."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
import pyarrow.parquet as pq

REPOSITORY = "tasksource/it-support-tickets"


def download(root: Path, client: httpx.Client | None = None) -> dict:
    manifest = root / "manifest.json"
    if manifest.exists():
        info = json.loads(manifest.read_text("utf-8"))
        if all(
            (root / name).is_file()
            and hashlib.sha256((root / name).read_bytes()).hexdigest() == checksum
            for name, checksum in info["sha256"].items()
        ):
            return info
    root.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    client = client or httpx.Client(
        timeout=60, follow_redirects=True, transport=httpx.HTTPTransport(retries=1)
    )
    try:
        response = client.get(f"https://huggingface.co/api/datasets/{REPOSITORY}")
        response.raise_for_status()
        revision = response.json()["sha"]
        checksums = {}
        for split in ("train", "test"):
            name = f"{split}.parquet"
            url = (
                f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{revision}/"
                f"data/{split}-00000-of-00001.parquet"
            )
            response = client.get(url)
            response.raise_for_status()
            temporary = root / f"{name}.part"
            temporary.write_bytes(response.content)
            frame = pd.read_parquet(temporary)
            validate_frame(frame)
            temporary.replace(root / name)
            checksums[name] = hashlib.sha256(response.content).hexdigest()
        info = {
            "source": f"https://huggingface.co/datasets/{REPOSITORY}",
            "original_source": "https://zenodo.org/records/7648117",
            "revision": revision,
            "downloaded_at": datetime.now(UTC).isoformat(),
            "license": "CC BY 4.0",
            "sha256": checksums,
            "purpose": "classification only; no severity or resolution labels",
        }
        manifest.write_text(json.dumps(info, indent=2), "utf-8")
        return info
    except (httpx.HTTPError, KeyError, ValueError, OSError) as exc:
        raise ValueError("Dataset unavailable or invalid; retry download-dataset later") from exc
    finally:
        if own_client:
            client.close()


def validate_frame(frame: pd.DataFrame) -> None:
    if not {"text", "label"}.issubset(frame.columns) or frame.empty:
        raise ValueError("Expected nonempty text and label columns")
    if frame[["text", "label"]].isna().any().any():
        raise ValueError("Missing ticket text or label")
    if not frame.text.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise ValueError("Ticket text must contain nonempty strings")


def load(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    manifest = root / "manifest.json"
    if not manifest.exists():
        raise ValueError("Run opspilot download-dataset --source it-support first")
    info = json.loads(manifest.read_text("utf-8"))
    frames = []
    for split in ("train", "test"):
        path = root / f"{split}.parquet"
        frame = pd.read_parquet(path)
        validate_frame(frame)
        metadata = pq.read_schema(path).metadata or {}
        hf = json.loads(metadata.get(b"huggingface", b"{}"))
        names = hf.get("info", {}).get("features", {}).get("label", {}).get("names")
        if names:
            frame["label"] = frame.label.map(lambda value, labels=names: labels[int(value)])
        else:
            frame["label"] = frame.label.astype(str)
        frame["split"] = split
        frames.append(frame)
    return frames[0], frames[1], info


def eda(root: Path, report_dir: Path) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    train, test, info = load(root)
    frame = pd.concat([train, test], ignore_index=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    counts = pd.crosstab(frame.label, frame.split)
    counts.to_csv(report_dir / "category_distribution.csv")
    summary = {
        "provenance": info,
        "rows": len(frame),
        "splits": frame.split.value_counts().to_dict(),
        "categories": sorted(frame.label.unique().tolist()),
        "missing_values": frame.isna().sum().to_dict(),
        "duplicate_texts": int(frame.text.duplicated().sum()),
        "cross_split_duplicate_texts": len(set(train.text) & set(test.text)),
        "length": frame.text.str.len().describe().to_dict(),
        "languages": "Not estimated: detection is unreliable for short multilingual tickets",
        "examples": [
            {"text": anonymize(row.text[:180]), "label": row.label}
            for row in frame.head(4).itertuples()
        ],
    }
    (report_dir / "dataset_summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    ax = counts.plot.bar(title="Authentic ticket categories by original split", figsize=(10, 5))
    ax.figure.tight_layout()
    ax.figure.savefig(report_dir / "category_distribution.png")
    plt.close(ax.figure)
    fig, ax = plt.subplots()
    ax.hist(frame.text.str.len(), bins=30)
    ax.set(xlabel="Characters", ylabel="Tickets", title="Authentic ticket length distribution")
    fig.tight_layout()
    fig.savefig(report_dir / "text_lengths.png")
    plt.close(fig)
    return summary


def anonymize(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[IP]", text)
    return re.sub(r"\b\d{4,}\b", "[NUMBER]", text)
