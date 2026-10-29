from typer.testing import CliRunner

from opspilot.cli import app
from opspilot.config import Settings


def test_config_uses_environment_and_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPSPILOT_API_TOKEN", "fixture-secret")
    settings = Settings(_env_file=None)
    assert settings.db_path.parent == tmp_path
    assert "fixture-secret" not in repr(settings)
    assert not settings.live_enabled


def test_cli_version():
    assert CliRunner().invoke(app, ["version"]).exit_code == 0
