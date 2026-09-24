"""Integration tests: remediation proposal and approval-gated execution."""

import pytest

from app.core.agent import Agent
from app.core.models import Diagnosis, Category, RiskLevel
from app.core.remediation_engine import RemediationEngine
from app.core.safety import ApprovalRequiredError


def test_proposals_ordered_low_risk_first():
    diag = Diagnosis(category=Category.INTERNET_DOWN, summary="x")
    proposals = RemediationEngine().propose(diag)
    assert proposals
    risks = [p.risk_level for p in proposals]
    # First proposal is never higher risk than the last.
    order = {RiskLevel.LOW: 0, RiskLevel.NONE: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}
    assert order[risks[0]] <= order[risks[-1]]


def test_proposals_only_from_category_whitelist():
    from app.knowledge.categories import get_category_spec

    diag = Diagnosis(category=Category.LOW_DISK_SPACE, summary="x")
    proposals = RemediationEngine().propose(diag)
    allowed = set(get_category_spec(Category.LOW_DISK_SPACE).remediation_tools)
    assert {p.tool for p in proposals}.issubset(allowed)


def test_execute_requires_approval(history):
    agent = Agent(history=history)
    session = agent.diagnose("My disk is almost full.").session
    assert session.proposals
    with pytest.raises(ApprovalRequiredError):
        agent.remediate_and_verify(session, session.proposals[0], approved=False)


def test_approved_execution_records_outcome_and_verifies(history):
    agent = Agent(history=history)
    session = agent.diagnose("My disk is almost full.").session
    proposal = session.proposals[0]
    updated = agent.remediate_and_verify(session, proposal, approved=True)
    assert updated.remediations[-1].executed is True
    assert updated.verification is not None
    assert updated.final_outcome  # a human-readable outcome was set


def test_next_proposal_advances_after_attempt(history):
    agent = Agent(history=history)
    session = agent.diagnose("My disk is almost full.").session
    first = session.proposals[0]
    agent.remediate_and_verify(session, first, approved=True)
    nxt = agent.next_proposal(session)
    assert nxt is None or nxt.tool != first.tool
