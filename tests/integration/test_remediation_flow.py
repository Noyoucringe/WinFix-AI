"""The approval-gated remediation workflow, end to end."""

import pytest

from app.core.agent import Agent
from app.core.models import SessionResult, SessionStatus
from app.core.safety import ApprovalRequiredError, SafetyError
from tests.scenarios import (
    SLOW_PC,
    SLOW_PC_AFTER_FIX_STILL_HIGH,
    STORAGE_AFTER_CLEANUP,
    STORAGE_FULL,
)


def test_nothing_runs_before_approval(scenario, history):
    scenario.use(SLOW_PC)
    agent = Agent(history=history, settle_seconds=0)
    session = agent.diagnose("My laptop is very slow").session
    assert session.status == SessionStatus.AWAITING_APPROVAL
    assert scenario.remediation_calls == []  # diagnosis never changes the PC
    with pytest.raises(ApprovalRequiredError):
        agent.remediate_and_verify(session, session.proposals[0], approved=False)
    assert scenario.remediation_calls == []
    assert session.remediations == []


def test_approved_fix_runs_exactly_once_with_resolved_arguments(scenario, history):
    scenario.use(SLOW_PC)
    agent = Agent(history=history, settle_seconds=0)
    session = agent.diagnose("My laptop is very slow").session
    agent.remediate_and_verify(session, session.proposals[0], approved=True)
    assert scenario.remediation_calls == [("restart_windows_search", {})]
    outcome = session.remediations[0]
    assert outcome.approved and outcome.executed and outcome.approved_at
    kinds = [e.kind for e in session.timeline]
    assert kinds[:3] == ["started", "checks", "diagnosis"]
    assert "approved" in kinds and "verified" in kinds


def test_decline_records_stopped_by_you(scenario, history):
    scenario.use(SLOW_PC)
    agent = Agent(history=history)
    session = agent.diagnose("My laptop is very slow").session
    agent.decline(session)
    stored = history.load_session(session.id)
    assert stored.result == SessionResult.STOPPED
    assert stored.approval_status == "declined"
    assert scenario.remediation_calls == []


def test_continue_investigation_offers_next_untried_fix(scenario, history):
    scenario.use(STORAGE_FULL, after_fix=STORAGE_AFTER_CLEANUP)
    agent = Agent(history=history, settle_seconds=0)
    session = agent.diagnose("My storage is almost full").session
    first = session.proposals[0]
    agent.remediate_and_verify(session, first, approved=True)
    assert session.result == SessionResult.NOT_RESOLVED
    agent.continue_investigation(session)
    assert session.proposals and session.proposals[0].tool != first.tool
    assert session.proposals[0].tool == "empty_recycle_bin"


def test_remediation_attempts_are_bounded(scenario, history):
    scenario.use(STORAGE_FULL, after_fix=STORAGE_AFTER_CLEANUP)
    agent = Agent(history=history, settle_seconds=0)
    agent.max_attempts = 1
    session = agent.diagnose("My storage is almost full").session
    agent.remediate_and_verify(session, session.proposals[0], approved=True)
    with pytest.raises(SafetyError):
        agent.remediate_and_verify(session, session.proposals[-1], approved=True)
    with pytest.raises(SafetyError):
        agent.continue_investigation(session)


def test_stop_after_unresolved_fix(scenario, history):
    scenario.use(SLOW_PC, after_fix=SLOW_PC_AFTER_FIX_STILL_HIGH)
    agent = Agent(history=history, settle_seconds=0)
    session = agent.diagnose("My laptop is very slow").session
    agent.remediate_and_verify(session, session.proposals[0], approved=True)
    agent.stop(session)
    stored = history.load_session(session.id)
    assert stored.result == SessionResult.STOPPED
    assert stored.finished_at is not None
    assert stored.changes_made == 1
