import json

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
