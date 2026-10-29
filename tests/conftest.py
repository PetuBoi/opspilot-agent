from pathlib import Path

import pytest

from opspilot.classifier import train_classifier
from opspilot.config import Settings
from opspilot.demo import seed
from opspilot.workflow import Investigator


@pytest.fixture(scope="session")
def trained_artifacts(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("models")
    train_classifier("demo", root / "demo", root / "reports")
    return root


@pytest.fixture()
def investigator(tmp_path, trained_artifacts):
    settings = Settings(data_dir=tmp_path / "runtime", api_token="test-local-token", _env_file=None)
    service = Investigator(settings, trained_artifacts)
    seed(service.store, settings.data_dir / "kb")
    service.kb.index(settings.data_dir / "kb")
    return service
