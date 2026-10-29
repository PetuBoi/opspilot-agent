"""Small transactional SQLite repository; all operational mutations remain fictional."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from opspilot.domain import AuditEvent, Ticket


class TransitionError(ValueError):
    """An investigation has an incompatible durable decision."""


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS health(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS investigations(
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions(
                    id TEXT PRIMARY KEY, approved INTEGER NOT NULL, note TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actions(
                    id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL,
                    tool TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, ticket_id TEXT, body TEXT);
                CREATE TABLE IF NOT EXISTS followups(
                    id TEXT PRIMARY KEY, ticket_id TEXT, body TEXT);
                CREATE TABLE IF NOT EXISTS audit(
                    id INTEGER PRIMARY KEY, investigation_id TEXT NOT NULL,
                    event TEXT NOT NULL, at TEXT NOT NULL, details TEXT NOT NULL,
                    UNIQUE(investigation_id,event));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, table: str, key: str, payload: dict) -> None:
        self._table(table)
        with self.connect() as db:
            db.execute(
                f"INSERT INTO {table}(id,payload) VALUES(?,?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (key, json.dumps(payload)),
            )

    def get(self, table: str, key: str) -> dict:
        self._table(table)
        with self.connect() as db:
            row = db.execute(f"SELECT payload FROM {table} WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def all(self, table: str) -> list[dict]:
        self._table(table)
        with self.connect() as db:
            return [
                json.loads(r[0]) for r in db.execute(f"SELECT payload FROM {table} ORDER BY id")
            ]

    @staticmethod
    def _table(table: str) -> None:
        if table not in {"tickets", "incidents", "health", "investigations"}:
            raise ValueError("Unknown repository collection")

    def ticket(self, key: str) -> Ticket:
        return Ticket.model_validate(self.get("tickets", key))

    def audit(self, key: str, event: str, details: dict | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO audit(investigation_id,event,at,details) VALUES(?,?,?,?)",
                (key, event, datetime.now(UTC).isoformat(), json.dumps(details or {})),
            )

    def audit_trail(self, key: str) -> list[AuditEvent]:
        with self.connect() as db:
            return [
                AuditEvent(event=r[0], at=r[1], details=json.loads(r[2]))
                for r in db.execute(
                    "SELECT event,at,details FROM audit WHERE investigation_id=? ORDER BY id",
                    (key,),
                )
            ]

    def decide(self, key: str, approved: bool, note: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT approved FROM decisions WHERE id=?", (key,)).fetchone()
            if row is not None and bool(row[0]) != approved:
                raise TransitionError("An opposite decision has already been recorded")
            db.execute("INSERT OR IGNORE INTO decisions VALUES(?,?,?)", (key, approved, note))
        self.audit(key, "approved" if approved else "rejected")

    def mutate(self, key: str, tool: str, ticket_id: str, body: str) -> dict:
        targets = {"attach_investigation_note": "notes", "create_followup_task": "followups"}
        if tool not in targets:
            raise ValueError("Tool is not in the mutation allowlist")
        action_id = f"{key}:{tool}"
        result = {"id": action_id, "tool": tool, "status": "completed"}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            decision = db.execute("SELECT approved FROM decisions WHERE id=?", (key,)).fetchone()
            if decision is None or not decision[0]:
                raise PermissionError("A persistent human approval is required")
            existing = db.execute("SELECT payload FROM actions WHERE id=?", (action_id,)).fetchone()
            if existing:
                return json.loads(existing[0])
            db.execute(f"INSERT INTO {targets[tool]} VALUES(?,?,?)", (action_id, ticket_id, body))
            db.execute(
                "INSERT INTO actions VALUES(?,?,?,?,?)",
                (action_id, key, tool, "completed", json.dumps(result)),
            )
            db.execute(
                "INSERT OR IGNORE INTO audit(investigation_id,event,at,details) VALUES(?,?,?,?)",
                (
                    key,
                    "action_completed",
                    datetime.now(UTC).isoformat(),
                    json.dumps({"action_id": action_id, "tool": tool}),
                ),
            )
        return result
