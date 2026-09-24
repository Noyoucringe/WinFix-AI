"""SQLite history: persistence, migrations, search, clear and reports."""

import json
import sqlite3

from app.core.agent import Agent
from app.core.history import SCHEMA_VERSION, HistoryStore
from app.core.models import Category, Diagnosis, Session, SessionResult, SessionStatus
from app.core.report import session_report
from tests.scenarios import SLOW_PC, SLOW_PC_AFTER_FIX_RESOLVED


def test_full_session_roundtrip(scenario, history):
    scenario.use(SLOW_PC, after_fix=SLOW_PC_AFTER_FIX_RESOLVED)
    agent = Agent(history=history, settle_seconds=0)
    session = agent.diagnose("My laptop is very slow").session
    agent.remediate_and_verify(session, session.proposals[0], approved=True)

    stored = history.load_session(session.id)
    assert stored.problem == "My laptop is very slow"
    assert stored.plan.category == Category.SLOW_COMPUTER
    assert len(stored.checks) >= 7 and stored.diagnostics
    assert stored.diagnosis.headline == "Your PC is experiencing memory pressure."
    assert stored.proposals[0].tool == "restart_windows_search"
    assert stored.approval_status == "approved"
    assert stored.remediations[0].approved_at is not None
    assert stored.verification.improved is True
    assert stored.result == SessionResult.RESOLVED
    assert stored.final_outcome.startswith("Search is working again.")
    assert [e.kind for e in stored.timeline][0] == "started"

    row = history.list_sessions()[0]
    assert row["display_id"] == session.display_id
    assert row["diagnosis"] == "Memory pressure"
    assert row["result"] == "resolved"
    assert row["changes_count"] == 1 and row["cloud_sent"] == 0


def test_search_and_filter(history):
    for problem, result in (("Wi-Fi keeps dropping", SessionResult.RESOLVED),
                            ("Storage almost full", SessionResult.NOT_RESOLVED),
                            ("100% disk_usage", SessionResult.RESOLVED)):
        history.save_session(Session(problem=problem, result=result))
    assert [r["problem"] for r in history.list_sessions(search="wi-fi")] == \
        ["Wi-Fi keeps dropping"]
    assert len(history.list_sessions(result="resolved")) == 2
    # LIKE wildcards in user input are treated literally.
    assert len(history.list_sessions(search="%")) == 1
    assert len(history.list_sessions(search="_")) == 1


def test_upsert_and_clear(history):
    s = Session(problem="p")
    history.save_session(s)
    s.status = SessionStatus.RESOLVED
    s.result = SessionResult.RESOLVED
    history.save_session(s)
    assert history.count() == 1
    assert history.list_sessions()[0]["result"] == "resolved"
    assert history.delete_all() == 1 and history.count() == 0


def test_migrates_a_version_1_database(tmp_path):
    path = tmp_path / "old.db"
    legacy = {"id": "abc", "created_at": "2026-09-01T10:00:00+00:00",
              "problem": "slow", "status": "resolved"}
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
            problem TEXT NOT NULL, category TEXT, status TEXT, diagnosis TEXT, fix TEXT,
            outcome TEXT, payload TEXT NOT NULL)""")
        conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?)",
                     ("abc", legacy["created_at"], "slow", None, "resolved", "", None, "",
                      json.dumps(legacy)))
    store = HistoryStore(path)
    assert store.schema_version == SCHEMA_VERSION
    assert store.list_sessions()[0]["result"] == "resolved"
    session = store.load_session("abc")
    assert session.result == SessionResult.RESOLVED
    assert session.display_id.startswith("WFX-")


def test_missing_session_returns_none(history):
    assert history.load_session("does-not-exist") is None


def test_report_is_readable_and_complete(scenario, history):
    scenario.use(SLOW_PC, after_fix=SLOW_PC_AFTER_FIX_RESOLVED)
    agent = Agent(history=history, settle_seconds=0)
    session = agent.diagnose("My laptop is very slow").session
    agent.remediate_and_verify(session, session.proposals[0], approved=True)
    text = session_report(session)
    for expected in (session.display_id, "Result:       Resolved", "Memory: 73.2%",
                     "Changes made", "restart_windows_search: applied",
                     "Windows Search service: Not responding → Running",
                     "Sent to cloud: Nothing", "Timeline"):
        assert expected in text


def test_short_label_for_no_issue():
    d = Diagnosis(category=Category.SLOW_COMPUTER, short_label="No problem found")
    assert Session(problem="x", diagnosis=d).short_diagnosis() == "No problem found"
