from fastapi.testclient import TestClient

from opspilot.api.app import create_app
from opspilot.config import Settings


def test_authenticated_end_to_end_api(investigator):
    client = TestClient(create_app(investigator.settings, investigator.artifact_root))
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/tickets").status_code == 401
    client.headers["Authorization"] = "Bearer test-local-token"
    assert len(client.get("/api/v1/tickets").json()) == 32
    assert client.get("/api/v1/tickets/DEMO-001").status_code == 200
    assert client.get("/api/v1/tickets/missing").status_code == 404
    assert client.post("/api/v1/tickets/analyze", json={"title": "x"}).status_code == 422
    response = client.post(
        "/api/v1/tickets/analyze",
        json={
            "ticket_id": "DEMO-001",
            "title": "Read existing ticket",
            "description": "Investigate selected existing ticket",
        },
    )
    assert response.status_code == 201
    key = response.json()["id"]
    assert client.get(f"/api/v1/investigations/{key}").json()["status"] == "pending"
    assert client.post(f"/api/v1/investigations/{key}/approve", json={}).status_code == 200
    assert client.post(f"/api/v1/investigations/{key}/approve", json={}).status_code == 200
    assert client.post(f"/api/v1/investigations/{key}/reject", json={}).status_code == 409
    assert client.get(f"/api/v1/investigations/{key}/audit").json()
    assert len(client.get("/api/v1/investigations").json()) == 1
    assert client.get("/api/v1/evaluation/summary").status_code == 200
    custom = client.post(
        "/api/v1/tickets/analyze",
        json={
            "title": "Email delivery delayed",
            "description": "Email delivery delayed all morning",
        },
    )
    assert custom.status_code == 201
    key2 = custom.json()["id"]
    assert client.post(f"/api/v1/investigations/{key2}/reject", json={}).status_code == 200
    assert client.get("/api/v1/investigations/missing/audit").status_code == 404
    live = client.post(
        "/api/v1/tickets/analyze",
        json={"title": "test live", "description": "not enabled", "mode": "live"},
    )
    assert live.status_code == 422


def test_unconfigured_auth_fails_closed(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path, api_token="", _env_file=None)))
    assert client.get("/api/v1/tickets").status_code == 503
