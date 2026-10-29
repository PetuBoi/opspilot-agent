"""Validated public domain schemas; severity is never inferred from category."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TicketInput(Schema):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=12000)
    severity: Literal["unknown", "low", "medium", "high", "critical"] = "unknown"
    propose_action: bool = True
    mode: Literal["offline", "live"] = "offline"


class Ticket(TicketInput):
    id: str
    origin: str = "user"


class Evidence(Schema):
    document_id: str
    chunk_id: str
    source: str
    text: str
    score: float
    metadata: dict[str, str] = Field(default_factory=dict)


class Prediction(Schema):
    label: str
    model: str
    dataset: str
    probability: float | None = None


class AnalysisRequest(TicketInput):
    ticket_id: str | None = Field(default=None, max_length=80)


class Decision(Schema):
    note: str = Field(default="", max_length=1000)


class Investigation(Schema):
    id: str
    ticket: Ticket
    status: Literal["pending", "completed", "rejected", "failed"]
    classification: Prediction
    evidence: list[Evidence]
    history: list[dict]
    service_health: dict
    summary: str
    steps: list[str]
    citations: list[str]
    action: dict | None
    generation: str
    warnings: list[str]
    elapsed_ms: float
    workflow_nodes: list[str]


class AuditEvent(Schema):
    event: str
    at: str
    details: dict
