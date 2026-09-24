"""SQLite-backed troubleshooting history (the local audit log).

One row per session. The complete session (problem, checks, evidence,
diagnosis, proposals, approval, remediation, verification, timeline and cloud
transmission record) is stored as JSON; the fields History lists and filters
on are promoted to columns. Schema changes are applied as numbered
migrations tracked with ``PRAGMA user_version``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging_setup import get_logger
from app.core.models import Session, SessionResult

logger = get_logger(__name__)


class HistoryError(Exception):
    """History couldn't be read or written."""


def _v1(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, problem TEXT NOT NULL,
            category TEXT, status TEXT, diagnosis TEXT, fix TEXT, outcome TEXT,
            payload TEXT NOT NULL)""")


_LEGACY_RESULTS = {"resolved": "resolved", "unresolved": "not_resolved",
                   "cancelled": "stopped", "failed": "failed"}


def _v2(conn: sqlite3.Connection) -> None:
    for column, kind in (("display_id", "TEXT"), ("result", "TEXT"), ("finished_at", "TEXT"),
                         ("checks_count", "INTEGER DEFAULT 0"),
                         ("changes_count", "INTEGER DEFAULT 0"),
                         ("cloud_sent", "INTEGER DEFAULT 0")):
        existing = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
        if column not in existing:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {column} {kind}")
    for status, result in _LEGACY_RESULTS.items():
        conn.execute("UPDATE sessions SET result=? WHERE result IS NULL AND status=?",
                     (result, status))
    conn.execute("UPDATE sessions SET result='in_progress' WHERE result IS NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at)")


MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_v1, _v2]
SCHEMA_VERSION = len(MIGRATIONS)


class HistoryStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or get_settings().database_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _migrate(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0 and conn.execute(
                    "SELECT name FROM sqlite_master WHERE name='sessions'").fetchone():
                version = 1  # a database created before versioning existed
            for number, migration in enumerate(MIGRATIONS, start=1):
                if number > version:
                    migration(conn)
                    conn.execute(f"PRAGMA user_version={number}")
                    logger.info("history migrated", extra={"component": "history",
                                                           "event": f"schema_v{number}"})

    @property
    def schema_version(self) -> int:
        with self._connect() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]

    # --- writes ------------------------------------------------------------
    def save_session(self, session: Session) -> None:
        category = session.diagnosis.category.value if session.diagnosis else (
            session.plan.category.value if session.plan else None)
        fix = session.remediations[-1].tool if session.remediations else (
            session.proposals[0].tool if session.proposals else None)
        row = (
            session.id, session.created_at.isoformat(), session.problem, category,
            session.status.value, session.short_diagnosis(), fix, session.final_outcome,
            session.model_dump_json(), session.display_id, session.result.value,
            session.finished_at.isoformat() if session.finished_at else None,
            sum(1 for c in session.checks if c.status == "completed"),
            session.changes_made, int(session.cloud.sent),
        )
        try:
            with self._lock, self._connect() as conn:
                conn.execute("""
                    INSERT INTO sessions (id, created_at, problem, category, status,
                        diagnosis, fix, outcome, payload, display_id, result, finished_at,
                        checks_count, changes_count, cloud_sent)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET category=excluded.category,
                        status=excluded.status, diagnosis=excluded.diagnosis,
                        fix=excluded.fix, outcome=excluded.outcome, payload=excluded.payload,
                        result=excluded.result, finished_at=excluded.finished_at,
                        checks_count=excluded.checks_count,
                        changes_count=excluded.changes_count, cloud_sent=excluded.cloud_sent
                    """, row)
        except sqlite3.Error as exc:
            logger.error("history write failed", extra={"component": "history",
                                                        "status": str(exc)[:200]})
            raise HistoryError("Couldn't save this session to history.") from exc

    def delete_all(self) -> int:
        with self._lock, self._connect() as conn:
            count = conn.execute("DELETE FROM sessions").rowcount
        logger.info("history cleared", extra={"component": "history", "event": "clear"})
        return count

    def delete_session(self, session_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))

    # --- reads -------------------------------------------------------------
    def list_sessions(self, limit: int = 200, *, search: str = "",
                      result: str | None = None) -> list[dict[str, Any]]:
        sql = ["""SELECT id, display_id, created_at, finished_at, problem, category, status,
                         result, diagnosis, fix, outcome, checks_count, changes_count,
                         cloud_sent FROM sessions WHERE 1=1"""]
        params: list[Any] = []
        if search:
            sql.append("AND (problem LIKE ? ESCAPE '\\' OR diagnosis LIKE ? ESCAPE '\\')")
            needle = "%" + search.replace("\\", "\\\\").replace("%", "\\%")\
                .replace("_", "\\_") + "%"
            params += [needle, needle]
        if result:
            sql.append("AND result = ?")
            params.append(result)
        sql.append("ORDER BY created_at DESC LIMIT ?")
        params.append(limit)
        with self._lock, self._connect() as conn:
            return [dict(r) for r in conn.execute(" ".join(sql), params).fetchall()]

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT payload FROM sessions WHERE id = ?",
                               (session_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def load_session(self, session_id: str) -> Session | None:
        payload = self.get_session(session_id)
        if payload is None:
            return None
        try:
            session = Session.model_validate(payload)
        except ValidationError as exc:
            logger.error("history record unreadable", extra={"component": "history",
                                                             "status": str(exc)[:200]})
            return None
        if session.result == SessionResult.IN_PROGRESS and \
                session.status.value in _LEGACY_RESULTS:
            session.result = SessionResult(_LEGACY_RESULTS[session.status.value])
        return session
