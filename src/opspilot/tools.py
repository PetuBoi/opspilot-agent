"""Explicit tool boundary. Retrieved content cannot register tools or grant authority."""

from opspilot.domain import Evidence
from opspilot.retrieval import KnowledgeBase
from opspilot.store import Store

READ_TOOLS = frozenset(
    {
        "search_knowledge_base",
        "get_historical_incidents",
        "get_service_health",
        "get_ticket_details",
        "draft_incident_note",
    }
)
WRITE_TOOLS = frozenset({"create_followup_task", "attach_investigation_note"})


class Tools:
    def __init__(self, store: Store, kb: KnowledgeBase):
        self.store, self.kb = store, kb

    def search_knowledge_base(self, query: str, top_k: int) -> list[Evidence]:
        return self.kb.search(query, top_k)

    def get_historical_incidents(self, service: str) -> list[dict]:
        return [r for r in self.store.all("incidents") if r["service"] == service][:3]

    def get_service_health(self, service: str) -> dict:
        try:
            return self.store.get("health", service)
        except KeyError:
            return {"service": service, "status": "unknown", "origin": "no observation"}

    def get_ticket_details(self, ticket_id: str) -> dict:
        return self.store.ticket(ticket_id).model_dump()

    @staticmethod
    def draft_incident_note(summary: str, citations: list[str]) -> str:
        return (
            f"Investigation draft (review required):\n{summary}\nEvidence: {', '.join(citations)}"
        )

    def execute(self, key: str, tool: str, ticket_id: str, body: str) -> dict:
        if tool not in WRITE_TOOLS:
            raise ValueError("Unknown or unauthorized state-changing tool")
        return self.store.mutate(key, tool, ticket_id, body)
