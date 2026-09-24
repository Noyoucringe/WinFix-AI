"""SQLite-backed session history and audit log.

Stores one row per troubleshooting session capturing the full audit trail:
problem, diagnostics, diagnosis, approval, remediation, verification, and
outcome. The full session is stored as JSON for fidelity, with key fields
promoted to columns for listing/filtering.

No sensitive personal information is stored deliberately; the payload is the
diagnostic evidence the app already collected.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging_setup import get_logger
from app.core.models import Session

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    problem       TEXT NOT NULL,
    category      TEXT,
    status        TEXT,
    diagnosis     TEXT,
    fix           TEXT,
    outcome       TEXT,
    payload       TEXT NOT NULL
);
"""


class HistoryStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or get_settings().database_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)

    def save_session(self, session: Session) -> None:
        payload = session.model_dump(mode="json")
        category = session.diagnosis.category.value if session.diagnosis else None
        diagnosis = session.short_diagnosis()
        fix = session.remediations[-1].tool if session.remediations else None
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (id, created_at, problem, category, status, diagnosis, fix,
                     outcome, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status, diagnosis=excluded.diagnosis,
                    category=excluded.category, fix=excluded.fix,
                    outcome=excluded.outcome, payload=excluded.payload
                """,
                (
                    session.id,
                    session.created_at.isoformat(),
                    session.problem,
                    category,
                    session.status.value,
                    diagnosis,
                    fix,
                    session.final_outcome,
                    json.dumps(payload),
                ),
            )
        logger.info(
            "session saved",
            extra={"component": "history", "event": "save", "status": session.status.value},
        )

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT id, created_at, problem, category, status, diagnosis, fix,
                          outcome
                   FROM sessions ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        return json.loads(row["payload"])

    def load_session(self, session_id: str) -> Session | None:
        payload = self.get_session(session_id)
        return Session.model_validate(payload) if payload else None
