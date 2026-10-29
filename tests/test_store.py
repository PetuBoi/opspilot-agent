import pytest
from pydantic import ValidationError

from opspilot.demo import seed
from opspilot.domain import TicketInput
from opspilot.store import Store, TransitionError


def test_demo_reseed_and_persistence(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    assert seed(store, tmp_path / "kb")["tickets"] == 32
    seed(store, tmp_path / "kb")
    assert len(Store(store.path).all("incidents")) == 32
    assert len(list((tmp_path / "kb").glob("*.md"))) == 24
    assert store.ticket("DEMO-001").origin == "SYNTHETIC"
    with pytest.raises(KeyError):
        store.ticket("missing")
    with pytest.raises(ValueError):
        store.all("notes; DROP TABLE tickets")


def test_durable_approval_idempotency_and_rejection(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    with pytest.raises(PermissionError):
        store.mutate("one", "attach_investigation_note", "ticket", "safe note")
    with pytest.raises(ValueError):
        store.mutate("one", "shell", "ticket", "anything")
    store.decide("one", True, "reviewed")
    first = store.mutate("one", "attach_investigation_note", "ticket", "safe note")
    assert store.mutate("one", "attach_investigation_note", "ticket", "other") == first
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
    store.decide("one", True, "replay")
    with pytest.raises(TransitionError):
        store.decide("one", False, "opposite")
    store.decide("two", False, "rejected")
    with pytest.raises(PermissionError):
        store.mutate("two", "create_followup_task", "ticket", "body")
    assert [e.event for e in store.audit_trail("one")] == ["approved", "action_completed"]


def test_input_limits():
    with pytest.raises(ValidationError):
        TicketInput(title="ok", description="x" * 13000)
    with pytest.raises(ValidationError):
        TicketInput(title="   ", description="     ")
