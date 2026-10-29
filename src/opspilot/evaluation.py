"""Measured synthetic retrieval/agent evaluation, separate from authentic classification."""

import json
import statistics
import tempfile
from pathlib import Path

from opspilot.config import Settings
from opspilot.demo import seed
from opspilot.domain import TicketInput
from opspilot.workflow import Investigator


def evaluate_agent(settings: Settings, artifacts: Path, report_dir: Path) -> dict:
    # Isolated DB: benchmarks never mutate or clear the user's investigation history.
    with tempfile.TemporaryDirectory(prefix="opspilot-eval-") as temporary:
        config = Settings(
            data_dir=Path(temporary),
            classifier_dataset="demo",
            _env_file=None,
            top_k=settings.top_k,
            chunk_size=settings.chunk_size,
        )
        service = Investigator(config, artifacts)
        seed(service.store, config.data_dir / "kb")
        service.kb.index(config.data_dir / "kb", config.chunk_size)
        queries = json.loads((config.data_dir / "retrieval_eval.json").read_text("utf-8"))
        recall, rr, sources, complete, approval, citations, replay, latencies = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
        details = []
        for i, item in enumerate(queries):
            retrieved = service.kb.search(item["query"], config.top_k)
            ids = [e.document_id for e in retrieved]
            relevant = set(item["relevant_documents"])
            recall.append(len(set(ids) & relevant) / len(relevant))
            rr.append(next((1 / (j + 1) for j, value in enumerate(ids) if value in relevant), 0))
            sources.append(all((config.data_dir / "kb" / e.source).is_file() for e in retrieved))
            result = service.analyze(TicketInput(title=item["query"], description=item["query"]))
            with service.store.connect() as db:
                count = db.execute(
                    "SELECT COUNT(*) FROM actions WHERE investigation_id=?", (result.id,)
                ).fetchone()[0]
            approval.append(result.status == "pending" and count == 0)
            citations.extend(c in {e.chunk_id for e in result.evidence} for c in result.citations)
            approved = i % 2 == 0
            final = service.resume(result.id, approved)
            again = service.resume(result.id, approved)
            complete.append(final.status in {"completed", "rejected"})
            with service.store.connect() as db:
                action_count = db.execute(
                    "SELECT COUNT(*) FROM actions WHERE investigation_id=?", (result.id,)
                ).fetchone()[0]
            replay.append(again == final and action_count == int(approved))
            latencies.append(final.elapsed_ms)
            details.append(
                {
                    "query": item["query"],
                    "relevant": sorted(relevant),
                    "retrieved": ids,
                    "status": final.status,
                    "elapsed_ms": final.elapsed_ms,
                }
            )
        summary = {
            "origin": "SYNTHETIC fixture evaluation; no real resolution ground truth",
            "queries": len(queries),
            "top_k": config.top_k,
            "retrieval_recall_at_k": statistics.mean(recall),
            "retrieval_mrr": statistics.mean(rr),
            "source_validity": statistics.mean(sources),
            "workflow_completion_rate": statistics.mean(complete),
            "approval_enforcement_rate": statistics.mean(approval),
            "citation_validity": statistics.mean(citations),
            "unsupported_citation_rate": 1 - statistics.mean(citations),
            "action_idempotency_rate": statistics.mean(replay),
            "mean_processing_ms": statistics.mean(latencies),
            "cases": details,
            "limitations": "24 runbook-title queries; no production resolution accuracy claim",
        }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "agent_summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    return summary
