"""Genuine stateful LangGraph execution with durable interruption and replay-safe actions."""

import hashlib
import time
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from filelock import FileLock
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from opspilot.classifier import Classifier
from opspilot.config import Settings, log_event
from opspilot.domain import Evidence, Investigation, Ticket, TicketInput
from opspilot.retrieval import KnowledgeBase
from opspilot.store import Store, TransitionError
from opspilot.tools import Tools


class State(TypedDict, total=False):
    id: str
    ticket: dict
    classification: dict
    evidence: list[dict]
    history: list[dict]
    service: str
    service_health: dict
    summary: str
    citations: list[str]
    steps: list[str]
    action: dict | None
    approved: bool
    status: str
    generation: str
    warnings: list[str]
    elapsed_ms: float
    started: float
    workflow_nodes: list[str]


class Investigator:
    def __init__(self, settings: Settings, artifact_root: Path = Path("artifacts")):
        self.settings = settings
        self.store = Store(settings.db_path)
        self.kb = KnowledgeBase(self.store)
        self.tools = Tools(self.store, self.kb)
        self.artifact_root = artifact_root

    @staticmethod
    def trace(state: State, node: str, **changes) -> dict:
        return {"workflow_nodes": [*state.get("workflow_nodes", []), node], **changes}

    def build(self, checkpointer):
        graph = StateGraph(State)
        nodes = [
            ("validate_ticket", self.validate),
            ("classify_incident", self.classify),
            ("retrieve_knowledge", self.retrieve),
            ("search_historical_incidents", self.history),
            ("inspect_service_health", self.health),
            ("synthesize_findings", self.synthesize),
            ("validate_evidence", self.evidence_check),
            ("suggest_resolution", self.suggest),
            ("propose_action", self.propose),
            ("approval_gate", self.approval),
            ("execute_approved_action", self.execute),
            ("audit_result", self.finish),
        ]
        for name, function in nodes:
            graph.add_node(name, function)
        graph.add_edge(START, "validate_ticket")
        for (left, _), (right, _) in zip(nodes[:8], nodes[1:9], strict=True):
            graph.add_edge(left, right)
        graph.add_conditional_edges(
            "propose_action",
            lambda s: "approval_gate" if s["action"] else "audit_result",
            ["approval_gate", "audit_result"],
        )
        graph.add_conditional_edges(
            "approval_gate",
            lambda s: "execute_approved_action" if s["approved"] else "audit_result",
            ["execute_approved_action", "audit_result"],
        )
        graph.add_edge("execute_approved_action", "audit_result")
        graph.add_edge("audit_result", END)
        return graph.compile(checkpointer=checkpointer)

    def validate(self, state: State) -> dict:
        ticket = Ticket.model_validate(state["ticket"])
        self.store.audit(state["id"], "validated", {"ticket_id": ticket.id})
        return self.trace(state, "validate_ticket")

    def classify(self, state: State) -> dict:
        ticket = Ticket.model_validate(state["ticket"])
        prediction = Classifier(self.artifact_root / self.settings.classifier_dataset).predict(
            f"{ticket.title}. {ticket.description}"
        )
        # Real taxonomy has no invented mapping to the fictional service taxonomy.
        return self.trace(state, "classify_incident", classification=prediction.model_dump())

    def retrieve(self, state: State) -> dict:
        ticket = state["ticket"]
        evidence = self.tools.search_knowledge_base(
            f"{ticket['title']} {ticket['description']}", self.settings.top_k
        )
        service = evidence[0].metadata["service"] if evidence else "unknown"
        return self.trace(
            state,
            "retrieve_knowledge",
            evidence=[e.model_dump() for e in evidence],
            service=service,
        )

    def history(self, state: State) -> dict:
        return self.trace(
            state,
            "search_historical_incidents",
            history=self.tools.get_historical_incidents(state["service"]),
        )

    def health(self, state: State) -> dict:
        return self.trace(
            state,
            "inspect_service_health",
            service_health=self.tools.get_service_health(state["service"]),
        )

    def synthesize(self, state: State) -> dict:
        evidence = [Evidence.model_validate(e) for e in state["evidence"]]
        citations = [e.chunk_id for e in evidence]
        warnings = ["Service health and historical resolutions are SYNTHETIC frozen fixtures."]
        summary = (
            (
                f"Classification: {state['classification']['label']}. "
                f"Retrieved {len(evidence)} documents. Fixture health: "
                f"{state['service_health']['status']}. Evidence suggests a service investigation, "
                "not a confirmed diagnosis or verified resolution. Human review is required."
            )
            if evidence
            else "Insufficient evidence. Escalate to a human; no diagnosis can be grounded."
        )
        generation = "OFFLINE TEMPLATE — non-LLM output"
        if not evidence:
            warnings.append("No relevant evidence was retrieved.")
        if state["ticket"]["mode"] == "live":
            from opspilot.live import summarize

            result = summarize(self.settings, state["ticket"]["description"], evidence)
            summary, citations, generation = (
                result.summary,
                result.citations,
                "LIVE LLM — unverified draft",
            )
        return self.trace(
            state,
            "synthesize_findings",
            summary=summary,
            citations=citations,
            generation=generation,
            warnings=warnings,
        )

    def evidence_check(self, state: State) -> dict:
        allowed = {e["chunk_id"] for e in state["evidence"]}
        if not set(state["citations"]) <= allowed or not self.kb.valid_citations(
            state["citations"]
        ):
            raise ValueError("Investigation contains unsupported or stale evidence references")
        return self.trace(state, "validate_evidence")

    def suggest(self, state: State) -> dict:
        # Trusted steps are application policy; document instructions are never executable.
        steps = [
            "Confirm incident scope, onset and user-reported severity.",
            "Review the cited runbook checks as untrusted reference material.",
            "Compare sanitized observations with service health timestamps.",
            "Escalate uncertain findings to the service owner before operational changes.",
        ]
        return self.trace(state, "suggest_resolution", steps=steps)

    def propose(self, state: State) -> dict:
        action = None
        if state["ticket"]["propose_action"] and state["evidence"]:
            action = {
                "tool": "attach_investigation_note",
                "status": "awaiting_approval",
                "body": self.tools.draft_incident_note(state["summary"], state["citations"]),
            }
        return self.trace(
            state, "propose_action", action=action, status="pending" if action else "completed"
        )

    def approval(self, state: State) -> dict:
        decision = interrupt(
            {
                "action": state["action"],
                "investigation_id": state["id"],
                "message": "Explicit human approval required for local mutation",
            }
        )
        approved = decision["approved"] is True
        self.store.decide(state["id"], approved, decision.get("note", ""))
        return self.trace(state, "approval_gate", approved=approved)

    def execute(self, state: State) -> dict:
        action = state["action"]
        result = self.tools.execute(
            state["id"], action["tool"], state["ticket"]["id"], action["body"]
        )
        return self.trace(state, "execute_approved_action", action={**action, **result})

    def finish(self, state: State) -> dict:
        status = "rejected" if state.get("approved") is False else "completed"
        action = state["action"]
        if status == "rejected" and action:
            action = {**action, "status": "rejected"}
        self.store.audit(state["id"], "workflow_finished", {"status": status})
        return self.trace(state, "audit_result", status=status, action=action)

    def analyze(self, request: TicketInput, ticket_id: str | None = None) -> Investigation:
        if request.mode == "live" and not self.settings.live_enabled:
            raise ValueError(
                "Live mode is disabled; enable it explicitly in environment configuration"
            )
        key = str(uuid4())
        ticket = (
            self.store.ticket(ticket_id)
            if ticket_id
            else Ticket(
                **request.model_dump(include=set(TicketInput.model_fields)),
                id=f"USER-{uuid4().hex[:12]}",
            )
        )
        # Existing ticket text is authoritative; request controls only execution options.
        ticket = ticket.model_copy(
            update={"propose_action": request.propose_action, "mode": request.mode}
        )
        self.store.put("tickets", ticket.id, ticket.model_dump())
        start = time.perf_counter()
        with SqliteSaver.from_conn_string(
            str(self.settings.data_dir / "checkpoints.sqlite")
        ) as saver:
            graph = self.build(saver)
            graph.invoke(
                {"id": key, "ticket": ticket.model_dump(), "workflow_nodes": []},
                {"configurable": {"thread_id": key}, "recursion_limit": 25},
            )
            state = graph.get_state({"configurable": {"thread_id": key}}).values
        state["elapsed_ms"] = (time.perf_counter() - start) * 1000
        return self.persist(state)

    def persist(self, state: dict) -> Investigation:
        result = Investigation.model_validate({k: state[k] for k in Investigation.model_fields})
        self.store.put("investigations", result.id, result.model_dump())
        log_event("investigation_saved", id=result.id, elapsed_ms=result.elapsed_ms)
        return result

    def get(self, key: str) -> Investigation:
        return Investigation.model_validate(self.store.get("investigations", key))

    def resume(self, key: str, approved: bool, note: str = "") -> Investigation:
        locks = self.settings.data_dir / "locks"
        locks.mkdir(exist_ok=True)
        lock = locks / f"{hashlib.sha256(key.encode()).hexdigest()}.lock"
        with FileLock(lock, timeout=15):
            existing = self.get(key)
            if existing.status != "pending":
                expected = "completed" if approved else "rejected"
                if existing.status != expected or not existing.action:
                    raise TransitionError("Investigation is not awaiting this decision")
                return existing
            self.store.decide(key, approved, note)
            start = time.perf_counter()
            with SqliteSaver.from_conn_string(
                str(self.settings.data_dir / "checkpoints.sqlite")
            ) as saver:
                graph = self.build(saver)
                config = {"configurable": {"thread_id": key}, "recursion_limit": 25}
                snapshot = graph.get_state(config)
                command = (
                    Command(resume={"approved": approved, "note": note})
                    if any(task.interrupts for task in snapshot.tasks)
                    else None
                )
                graph.invoke(command, config)
                state = graph.get_state(config).values
            state["elapsed_ms"] = existing.elapsed_ms + (time.perf_counter() - start) * 1000
            return self.persist(state)
