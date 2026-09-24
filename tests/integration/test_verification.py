"""Verification: re-measure, re-analyze, and report honestly."""

import pytest

from app.core.agent import Agent
from app.core.models import CheckStatus, RemediationOutcome, SessionResult
from app.core.result import error_result
from app.core.verification_engine import VerificationEngine
from tests.scenarios import (
    SLOW_PC,
    SLOW_PC_AFTER_FIX_RESOLVED,
    SLOW_PC_AFTER_FIX_STILL_HIGH,
    STORAGE_AFTER_CLEANUP,
    STORAGE_FULL,
    DNS_BROKEN,
    DNS_FIXED,
)


def _diagnose(scenario, evidence, after, problem):
    scenario.use(evidence, after_fix=after)
    agent = Agent(settle_seconds=0)
    session = agent.diagnose(problem).session
    return agent, session


def test_success_matches_design(scenario):
    agent, session = _diagnose(scenario, SLOW_PC, SLOW_PC_AFTER_FIX_RESOLVED,
                               "My laptop is very slow")
    proposal = session.proposals[0]
    assert proposal.tool == "restart_windows_search"
    session = agent.remediate_and_verify(session, proposal, approved=True)
    v = session.verification
    assert v.improved is True and v.action_effective is True
    assert v.headline == "Search is working again."
    rows = {c.label: c for c in v.checks}
    assert rows["Windows Search service"].before == "Not responding"
    assert rows["Windows Search service"].after == "Running"
    assert rows["Search indexer memory"].before == "2.1 GB"
    assert rows["Search indexer memory"].after == "96 MB"
    assert rows["Memory in use"].before == "73.2% · 11.5 GB"
    assert rows["Memory in use"].after == "60.5% · 9.5 GB"
    assert "released 2.0 GB of memory" in v.summary
    assert session.result == SessionResult.RESOLVED


def test_fix_worked_but_issue_remains(scenario):
    agent, session = _diagnose(scenario, SLOW_PC, SLOW_PC_AFTER_FIX_STILL_HIGH,
                               "My laptop is very slow")
    session = agent.remediate_and_verify(session, session.proposals[0], approved=True)
    v = session.verification
    assert v.improved is False
    assert v.action_effective is True  # the service did restart
    assert v.headline == "The first fix did not resolve the problem."
    assert "original issue is still present" in v.summary
    assert v.found.startswith("The fix worked as intended")
    assert "memory_pressure" in v.remaining_causes
    rows = {c.label: c for c in v.checks}
    assert rows["Memory in use"].after.endswith("Still high")
    assert "safe to keep" in v.note
    assert session.result == SessionResult.NOT_RESOLVED


def test_small_changes_are_noise_not_improvement():
    from tests.scenarios import results_for

    before = results_for(SLOW_PC)
    after = results_for(SLOW_PC_AFTER_FIX_STILL_HIGH)  # 73.2% -> 72.0%
    from app.core.verification_engine import CHECKS

    row = CHECKS["memory_in_use"].build(before, after)
    assert row.status == CheckStatus.UNCHANGED


def test_storage_cleanup_measures_freed_space(scenario):
    agent, session = _diagnose(scenario, STORAGE_FULL, STORAGE_AFTER_CLEANUP,
                               "My storage is almost full")
    session = agent.remediate_and_verify(session, session.proposals[0], approved=True)
    rows = {c.label: c for c in session.verification.checks}
    assert rows["Free space on C:"].before == "6.1 GB"
    assert rows["Free space on C:"].status == CheckStatus.IMPROVED
    assert rows["Temporary files"].after == "120 MB"
    # Space was freed, but the drive is still critically full: not resolved.
    assert session.verification.improved is False
    assert session.verification.action_effective is True


def test_dns_fix_resolves(scenario):
    agent, session = _diagnose(scenario, DNS_BROKEN, DNS_FIXED, "Websites won't load")
    session = agent.remediate_and_verify(session, session.proposals[0], approved=True)
    assert session.verification.improved is True
    assert session.verification.headline == "Websites resolve again."


def test_fix_that_could_not_be_applied_is_reported(scenario, monkeypatch):
    agent, session = _diagnose(scenario, SLOW_PC, SLOW_PC_AFTER_FIX_RESOLVED,
                               "My laptop is very slow")
    reg = agent.remediation.registry
    monkeypatch.setattr(reg, "execute_tool", lambda name, args=None: error_result(
        name, "ElevationDeclined", "Administrator permission was not granted."))
    session = agent.remediate_and_verify(session, session.proposals[0], approved=True)
    v = session.verification
    assert v.improved is False and v.action_effective is False
    assert v.headline == "The fix couldn't be applied."
    assert "nothing was changed" in v.summary.lower()


def test_verification_reruns_the_same_measurements(scenario):
    agent, session = _diagnose(scenario, SLOW_PC, SLOW_PC_AFTER_FIX_RESOLVED,
                               "My laptop is very slow")
    tools = agent.verification.tools_for(session, session.proposals[0])
    assert "get_memory_usage" in tools and "get_running_processes" in tools


def test_pending_rows_show_before_values(scenario):
    agent, session = _diagnose(scenario, SLOW_PC, SLOW_PC_AFTER_FIX_RESOLVED,
                               "My laptop is very slow")
    rows = agent.verification.pending_checks(session, session.proposals[0])
    assert rows and all(r.after == "Measuring…" for r in rows)
    assert rows[0].before == "Not responding"


def test_outcome_without_success_never_claims_resolution():
    engine = VerificationEngine()
    from app.core.models import RemediationProposal, Session

    outcome = RemediationOutcome(tool="flush_dns", approved=True, executed=True,
                                 success=False, error={"type": "CommandError",
                                                       "message": "boom"})
    result = engine.run(Session(problem="x"),
                        RemediationProposal(tool="flush_dns", title="t", reason="r"),
                        outcome)
    assert result.improved is False


@pytest.mark.parametrize("attempt,word", [(1, "first"), (2, "second")])
def test_failure_headline_counts_attempts(attempt, word):
    engine = VerificationEngine()
    from app.core.models import VerificationResult
    from app.knowledge.remediations import fix_info

    result = VerificationResult(action_effective=True)
    engine._write_copy(result, fix_info("flush_dns"), [], [], attempt, {})
    assert result.headline == f"The {word} fix did not resolve the problem."
