import httpx
import pytest

from opspilot.config import Settings
from opspilot.domain import Evidence
from opspilot.evaluation import evaluate_agent
from opspilot.live import summarize


def test_measured_agent_evaluation(tmp_path, trained_artifacts):
    summary = evaluate_agent(Settings(_env_file=None), trained_artifacts, tmp_path)
    assert summary["queries"] == 24
    assert summary["approval_enforcement_rate"] == 1
    assert summary["action_idempotency_rate"] == 1
    assert 0 <= summary["retrieval_mrr"] <= 1
    assert (tmp_path / "agent_summary.json").exists()


def test_live_opt_in_structured_output_and_invalid_citation(monkeypatch):
    with pytest.raises(ValueError, match="opt-in"):
        summarize(Settings(_env_file=None), "ticket", [])
    settings = Settings(
        live_enabled=True, llm_api_key="mock-secret", llm_model="mock-model", _env_file=None
    )
    response = {"choices": [{"message": {"content": '{"summary":"A draft","citations":["cid"]}'}}]}
    client_class = httpx.Client

    def make_client():
        return client_class(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
        )

    monkeypatch.setattr("opspilot.live.httpx.Client", lambda **_: make_client())
    evidence = Evidence(document_id="doc", chunk_id="cid", source="x.md", text="untrusted", score=1)
    assert summarize(settings, "ticket", [evidence]).citations == ["cid"]
    with pytest.raises(ValueError, match="failed validation"):
        summarize(settings, "ticket", [])
