"""Authenticated local API. No implicit initialization or provider execution on import."""

import json
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from filelock import Timeout

from opspilot.config import Settings
from opspilot.domain import AnalysisRequest, AuditEvent, Decision, Investigation, Ticket
from opspilot.store import TransitionError
from opspilot.workflow import Investigator


def create_app(
    settings: Settings | None = None, artifact_root: Path = Path("artifacts")
) -> FastAPI:
    settings = settings or Settings()
    api = FastAPI(title="OpsPilot", version="0.1.0", description="Fictional local IT operations")

    def service() -> Investigator:
        return Investigator(settings, artifact_root)

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = settings.api_token.get_secret_value()
        if not expected:
            raise HTTPException(503, "Set OPSPILOT_API_TOKEN to enable protected endpoints")
        token = (authorization or "").removeprefix("Bearer ")
        if not secrets.compare_digest(token, expected):
            raise HTTPException(
                401, "Invalid local API token", headers={"WWW-Authenticate": "Bearer"}
            )

    protected = [Depends(authorize)]

    @api.exception_handler(KeyError)
    async def missing(_: Request, __: KeyError):
        return JSONResponse(status_code=404, content={"detail": "Requested record not found"})

    @api.exception_handler(TransitionError)
    async def conflict(_: Request, exc: TransitionError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @api.exception_handler(ValueError)
    async def invalid(_: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @api.exception_handler(Timeout)
    async def busy(_: Request, __: Timeout):
        return JSONResponse(status_code=503, content={"detail": "Investigation busy; retry later"})

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "default_mode": "offline", "environment": "fictional"}

    @api.get("/api/v1/tickets", dependencies=protected, response_model=list[Ticket])
    def tickets():
        return service().store.all("tickets")

    @api.get("/api/v1/tickets/{ticket_id}", dependencies=protected, response_model=Ticket)
    def ticket(ticket_id: str):
        return service().store.ticket(ticket_id)

    @api.post(
        "/api/v1/tickets/analyze",
        dependencies=protected,
        response_model=Investigation,
        status_code=201,
    )
    def analyze(body: AnalysisRequest):
        return service().analyze(body, body.ticket_id)

    @api.get("/api/v1/investigations", dependencies=protected, response_model=list[Investigation])
    def investigations():
        return service().store.all("investigations")

    @api.get("/api/v1/investigations/{key}", dependencies=protected, response_model=Investigation)
    def investigation(key: str):
        return service().get(key)

    @api.post(
        "/api/v1/investigations/{key}/approve", dependencies=protected, response_model=Investigation
    )
    def approve(key: str, body: Decision):
        return service().resume(key, True, body.note)

    @api.post(
        "/api/v1/investigations/{key}/reject", dependencies=protected, response_model=Investigation
    )
    def reject(key: str, body: Decision):
        return service().resume(key, False, body.note)

    @api.get(
        "/api/v1/investigations/{key}/audit",
        dependencies=protected,
        response_model=list[AuditEvent],
    )
    def audit(key: str):
        instance = service()
        instance.get(key)
        return instance.store.audit_trail(key)

    @api.get("/api/v1/evaluation/summary", dependencies=protected)
    def evaluation() -> dict:
        files = {
            "synthetic_agent": Path("reports/synthetic/agent_summary.json"),
            "synthetic_classification": Path("reports/synthetic/classification_summary.json"),
            "real_classification": Path("reports/real/classification_summary.json"),
            "real_dataset": Path("reports/real/dataset_summary.json"),
        }
        return {
            key: json.loads(path.read_text("utf-8"))
            for key, path in files.items()
            if path.is_file()
        }

    return api


app = create_app()
