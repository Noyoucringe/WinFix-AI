"""Tests for the SQLite history/audit store."""

from app.core.models import (
    Category,
    Diagnosis,
    RemediationOutcome,
    Session,
    SessionStatus,
)


def test_save_and_load_roundtrip(history):
    session = Session(
        problem="slow pc",
        status=SessionStatus.DIAGNOSED,
        diagnosis=Diagnosis(category=Category.SLOW_COMPUTER, summary="high memory"),
    )
    history.save_session(session)
    loaded = history.load_session(session.id)
    assert loaded is not None
    assert loaded.problem == "slow pc"
    assert loaded.diagnosis.summary == "high memory"


def test_list_sessions_orders_and_promotes_columns(history):
    s = Session(problem="wifi", status=SessionStatus.RESOLVED,
                diagnosis=Diagnosis(category=Category.WIFI_DISCONNECTING, summary="dns"))
    s.remediations.append(RemediationOutcome(tool="flush_dns", approved=True,
                                             executed=True, success=True))
    s.final_outcome = "Fixed"
    history.save_session(s)
    rows = history.list_sessions()
    assert rows
    row = rows[0]
    assert row["problem"] == "wifi"
    assert row["category"] == "wifi_disconnecting"
    assert row["fix"] == "flush_dns"
    assert row["outcome"] == "Fixed"


def test_upsert_updates_existing(history):
    s = Session(problem="p", status=SessionStatus.CREATED)
    history.save_session(s)
    s.status = SessionStatus.RESOLVED
    history.save_session(s)
    rows = [r for r in history.list_sessions() if r["id"] == s.id]
    assert len(rows) == 1
    assert rows[0]["status"] == "resolved"


def test_missing_session_returns_none(history):
    assert history.load_session("does-not-exist") is None
