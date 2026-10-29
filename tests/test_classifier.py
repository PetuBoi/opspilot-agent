import json

import pandas as pd
import pytest

from opspilot.classifier import Classifier, frames, preprocess, train_classifier


def test_training_serialization_prediction_and_reports(tmp_path):
    output = tmp_path / "artifact"
    report = tmp_path / "report"
    metadata = train_classifier("demo", output, report)
    assert metadata["seed"] == 42
    assert metadata["test_rows"] == 24
    assert len(metadata["comparison"]) == 2
    classifier = Classifier(output)
    assert classifier.predict("VPN tunnel timeout").label == "vpn"
    assert classifier.predict("Laptop disk space").dataset == "demo"
    assert 0 <= metadata["comparison"][0]["accuracy"] <= 1
    assert json.loads((report / "classification_summary.json").read_text())["selected_model"]
    assert preprocess("  ＶＰＮ\nERROR  ") == "vpn error"
    with pytest.raises(ValueError):
        Classifier(tmp_path / "missing")
    with pytest.raises(ValueError):
        frames("unsupported")


def test_quarantined_category_remains_in_evaluation(tmp_path, monkeypatch):
    train = pd.DataFrame(
        [
            {"text": f"{topic} independent issue record {index}", "label": topic}
            for topic in ("vpn", "mail")
            for index in range(12)
        ]
        + [{"text": "identical retirement template", "label": "EOL"}]
    )
    test = pd.DataFrame(
        [
            {"text": "vpn new issue", "label": "vpn"},
            {"text": "mail delivery failure", "label": "mail"},
            {"text": "identical retirement template", "label": "EOL"},
        ]
    )
    monkeypatch.setattr(
        "opspilot.classifier.frames", lambda *_: (train, test, {"origin": "fixture"})
    )
    metadata = train_classifier("demo", tmp_path / "artifact", tmp_path / "report")
    assert metadata["labels_without_training_examples"] == ["EOL"]
    matrix = pd.read_csv(tmp_path / "report" / "linear_svc_confusion_matrix.csv", index_col=0)
    assert list(matrix.columns) == ["EOL", "mail", "vpn"]
    assert matrix.to_numpy().sum() == len(test)
    assert matrix.loc["EOL"].sum() == 1
