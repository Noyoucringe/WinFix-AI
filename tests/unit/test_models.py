"""Tests for the Pydantic domain models."""

from app.core.models import (
    Cause,
    Category,
    Diagnosis,
    RemediationProposal,
    RiskLevel,
    Session,
    SessionStatus,
)


def test_cause_likelihood_words():
    assert Cause(cause="a", confidence=0.9).likelihood_word == "likely"
    assert Cause(cause="a", confidence=0.5).likelihood_word == "possible"
    assert Cause(cause="a", confidence=0.1).likelihood_word == "less likely"


def test_diagnosis_top_cause():
    d = Diagnosis(possible_causes=[
        Cause(cause="low", confidence=0.3),
        Cause(cause="high", confidence=0.8),
    ])
    assert d.top_cause.cause == "high"


def test_diagnosis_no_causes():
    assert Diagnosis().top_cause is None


def test_session_defaults_and_roundtrip():
    s = Session(problem="slow", status=SessionStatus.DIAGNOSED,
                diagnosis=Diagnosis(category=Category.SLOW_COMPUTER, summary="s"))
    dumped = s.model_dump(mode="json")
    restored = Session.model_validate(dumped)
    assert restored.problem == "slow"
    assert restored.diagnosis.category == Category.SLOW_COMPUTER


def test_proposal_defaults():
    p = RemediationProposal(tool="flush_dns", title="Flush DNS", reason="because")
    assert p.risk_level == RiskLevel.LOW
    assert p.requires_admin is False
