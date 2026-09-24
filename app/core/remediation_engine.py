"""Remediation engine.

Proposes whitelisted fixes for a diagnosis and executes one only after the
safety layer confirms explicit user approval. Every execution is recorded as a
:class:`RemediationOutcome` for the audit trail.

Proposals are driven by evidence: each measured cause can link to one fix, and
a fix is only offered if the problem's category allows it. When no specific
fault was measured, a category may offer one general safe step, clearly marked
as not evidence-backed. Fixes whose required parameters can't be resolved from
the evidence are never offered (approving them could only fail).
"""

from __future__ import annotations

from typing import Any

from app.core.logging_setup import get_logger
from app.core.models import (
    Category,
    Cause,
    Diagnosis,
    Level,
    RemediationOutcome,
    RemediationProposal,
    RiskLevel,
    now_utc,
)
from app.core.safety import SafetyValidator
from app.core.tool_registry import get_registry
from app.knowledge import evidence as ev
from app.knowledge.categories import get_category_spec
from app.knowledge.remediations import fix_info

logger = get_logger(__name__)

_RISK_WORD = {RiskLevel.NONE: "No", RiskLevel.LOW: "Low", RiskLevel.MEDIUM: "Medium",
              RiskLevel.HIGH: "High"}


class RemediationEngine:
    def __init__(self, safety: SafetyValidator | None = None) -> None:
        self.registry = get_registry()
        self.safety = safety or SafetyValidator(self.registry)

    # --- proposals ---------------------------------------------------------
    def propose(
        self,
        diagnosis: Diagnosis,
        results: dict[str, Any] | None = None,
        *,
        exclude: set[str] | None = None,
    ) -> list[RemediationProposal]:
        spec = get_category_spec(diagnosis.category)
        allowed = set(spec.remediation_tools) if spec else set()
        exclude = exclude or set()
        results = results or {}
        proposals: list[RemediationProposal] = []
        seen: set[str] = set()

        for cause in diagnosis.possible_causes:
            tool = cause.remediation
            if (not tool or tool in seen or tool in exclude or tool not in allowed
                    or cause.level not in (Level.CAUTION, Level.CRITICAL)):
                continue
            proposal = self._build(tool, diagnosis, results, cause)
            if proposal:
                proposals.append(proposal)
                seen.add(tool)

        # A general step only makes sense when no specific fault was measured;
        # otherwise it could contradict the evidence (e.g. restarting a service
        # that was found disabled).
        if not proposals and spec and spec.general_fix and spec.general_fix not in exclude \
                and diagnosis.level in (Level.OK, Level.INFO):
            proposal = self._build(spec.general_fix, diagnosis, results, None)
            if proposal:
                proposals.append(proposal)
        return proposals

    def _build(self, tool: str, diagnosis: Diagnosis, results: dict[str, Any],
               cause: Cause | None) -> RemediationProposal | None:
        if not self.registry.has(tool):
            return None
        tspec = self.registry.get_tool(tool)
        params = self._resolve_parameters(tool, diagnosis, results)
        if params is None:
            logger.info("fix skipped: parameters unresolved",
                        extra={"component": "remediation", "event": "skip", "tool": tool})
            return None
        info = fix_info(tool)
        if cause:
            reason = cause.detail or cause.cause
            description = f"{cause.detail} {info.description}".strip()
        else:
            reason = ("No specific fault was measured. This is a safe, general step for "
                      "this kind of problem.")
            description = f"{reason} {info.description}"
        return RemediationProposal(
            tool=tool,
            title=info.title,
            reason=reason,
            risk_level=tspec.risk_level,
            requires_admin=tspec.requires_admin,
            parameters=params,
            verification_tools=list(info.verify_tools),
            consequences=info.risk_note,
            change=info.change,
            summary=info.summary,
            description=description,
            expected_effect=info.expected_effect,
            what_changes=info.what_changes.replace(
                "The network adapter", f"The network adapter '{params.get('adapter_name')}'")
            if "adapter_name" in params else info.what_changes,
            what_unchanged=info.what_unchanged,
            files_affected=info.files_affected,
            estimated_time=info.estimated_time,
            risk_note=f"{_RISK_WORD[tspec.risk_level]} · {info.risk_note}".strip(" ·"),
            steps=list(info.steps),
            technical=info.technical.replace("<adapter>", params.get("adapter_name", "<adapter>")),
            cause_id=cause.id if cause else None,
            evidence_backed=cause is not None,
        )

    def _resolve_parameters(self, tool: str, diagnosis: Diagnosis,
                            results: dict[str, Any]) -> dict[str, Any] | None:
        """Fill required parameters from evidence; None if they can't be."""
        spec = self.registry.get_tool(tool)
        required = [p.name for p in spec.parameters if p.required]
        if not required:
            return {}
        params: dict[str, Any] = {}
        for name in required:
            if name == "adapter_name":
                adapter = ev.pick_adapter(
                    results, prefer_wireless=diagnosis.category == Category.WIFI_DISCONNECTING)
                if not adapter:
                    return None
                params[name] = adapter
            else:
                return None  # e.g. 'pid': never guessed
        try:
            self.registry.validate_arguments(spec, params)
        except Exception:  # noqa: BLE001
            return None
        return params

    # --- execution ---------------------------------------------------------
    def execute(
        self,
        proposal: RemediationProposal,
        *,
        approved: bool,
        arguments: dict[str, Any] | None = None,
        runner=None,
    ) -> RemediationOutcome:
        """Execute an approved remediation. Raises if not approved.

        ``runner`` lets the caller route admin-only fixes through the UAC
        elevation helper; it receives (tool, arguments) and returns a result.
        """
        arguments = dict(proposal.parameters if arguments is None else arguments)
        outcome = RemediationOutcome(tool=proposal.tool, approved=approved,
                                     approved_at=now_utc() if approved else None)

        # Safety gate: registration, remediation-only, argument validity, approval.
        self.safety.validate_remediation(proposal.tool, approved=approved,
                                         arguments=arguments)

        outcome.executed = True
        if runner is not None:
            result, outcome.elevated = runner(proposal.tool, arguments)
        else:
            result = self.registry.execute_tool(proposal.tool, arguments)
        outcome.result = result
        outcome.success = bool(result.get("success"))
        outcome.finished_at = now_utc()
        if not outcome.success:
            outcome.error = result.get("error")
        logger.info("remediation executed",
                    extra={"component": "engine", "event": "remediation",
                           "tool": proposal.tool,
                           "status": "ok" if outcome.success else "fail"})
        return outcome
