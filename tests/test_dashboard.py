from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from opspilot.api.app import create_app


def test_dashboard_actual_logic(investigator, monkeypatch):
    client = TestClient(create_app(investigator.settings, investigator.artifact_root))
    monkeypatch.setenv("OPSPILOT_API_TOKEN", "test-local-token")

    def request(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return client.request(method, httpx.URL(url).raw_path.decode(), **kwargs)

    monkeypatch.setattr("httpx.request", request)
    app = AppTest.from_file(Path("apps/dashboard.py").resolve(), default_timeout=20).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["investigation"]["status"] == "pending"
    next(b for b in app.button if b.label == "Approve note attachment").click().run()
    assert not app.exception
    assert app.session_state["investigation"]["status"] == "completed"
