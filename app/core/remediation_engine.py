"""Remediation engine.

Proposes whitelisted remediation actions for a diagnosis and executes them —
but only after the safety layer confirms explicit user approval. Every
execution is recorded as a :class:`RemediationOutcome` for the audit trail.
"""

from __future__ import annotations

from typing import Any

from app.core.logging_setup import get_logger
from app.core.models import (
    Diagnosis,
    RemediationOutcome,
    RemediationProposal,
    RiskLevel,
)
from app.core.safety import SafetyValidator
from app.core.tool_registry import get_registry
from app.knowledge.categories import get_category_spec

logger = get_logger(__name__)

_RISK_CONSEQUENCE = {
    RiskLevel.NONE: "No system changes.",
    RiskLevel.LOW: "Low risk; easily reversible and safe to run.",
    RiskLevel.MEDIUM: "Moderate risk; may briefly interrupt connectivity or a service.",
    RiskLevel.HIGH: "Higher risk; a reboot may be required afterwards.",
}


class RemediationEngine:
    def __init__(self, safety: SafetyValidator | None = None) -> None:
        self.registry = get_registry()
        self.safety = safety or SafetyValidator(self.registry)

    def propose(self, diagnosis: Diagnosis) -> list[RemediationProposal]:
        """Build ordered remediation proposals for a diagnosis.

        Proposals come from the category's whitelisted remediation tools. They
        are ordered low-risk first so the safest fix is tried first.
        """
        spec = get_category_spec(diagnosis.category)
        if not spec:
            return []

        proposals: list[RemediationProposal] = []
        for tool_name in spec.remediation_tools:
            if not self.registry.has(tool_name):
                continue
            tspec = self.registry.get_tool(tool_name)
            reason = self._reason_for(diagnosis, tspec.description)
            proposals.append(
                RemediationProposal(
                    tool=tool_name,
                    title=tspec.description,
                    reason=reason,
                    risk_level=tspec.risk_level,
                    requires_admin=tspec.requires_admin,
                    verification_tools=list(spec.verification_tools),
                    consequences=_RISK_CONSEQUENCE.get(tspec.risk_level, ""),
                )
            )

        risk_order = {RiskLevel.LOW: 0, RiskLevel.NONE: 0, RiskLevel.MEDIUM: 1,
                      RiskLevel.HIGH: 2}
        proposals.sort(key=lambda p: risk_order.get(p.risk_level, 1))
        return proposals

    def _reason_for(self, diagnosis: Diagnosis, action_desc: str) -> str:
        top = diagnosis.top_cause
        if top:
            cause = top.cause[:1].lower() + top.cause[1:]
            return f"Recommended because {cause} ({top.likelihood_word})."
        return "A safe first step that commonly resolves this kind of problem."

    def execute(
        self,
        proposal: RemediationProposal,
        *,
        approved: bool,
        arguments: dict[str, Any] | None = None,
    ) -> RemediationOutcome:
        """Execute an approved remediation. Raises if not approved."""
        arguments = arguments or dict(proposal.parameters)
        outcome = RemediationOutcome(tool=proposal.tool, approved=approved)

        # Safety gate: validates registration, that it's a remediation tool,
        # argument validity, AND that the user approved it.
        self.safety.validate_remediation(
            proposal.tool, approved=approved, arguments=arguments
        )

        outcome.executed = True
        result = self.registry.execute_tool(proposal.tool, arguments)
        outcome.result = result
        outcome.success = bool(result.get("success"))
        if not outcome.success:
            outcome.error = result.get("error")
        logger.info(
            "remediation executed",
            extra={"component": "engine", "event": "remediation",
                   "tool": proposal.tool,
                   "status": "ok" if outcome.success else "fail"},
        )
        return outcome
