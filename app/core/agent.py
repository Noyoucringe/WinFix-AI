"""The WinFix troubleshooting agent.

Orchestrates the full workflow:

    diagnose → gather evidence → reason → recommend → (user approval) →
    remediate → verify → report

The agent is *bounded*: it never runs more than ``MAX_AGENT_STEPS`` diagnostic
steps and never more than ``MAX_REMEDIATION_ATTEMPTS`` fixes. It reasons about
which tools are relevant (via the planner/knowledge base) rather than blindly
running everything, and exposes concise, user-facing reasoning — never hidden
chain-of-thought.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.config import get_settings
from app.core.diagnostic_engine import DiagnosticEngine
from app.core.logging_setup import get_logger
from app.core.models import (
    Category,
    RemediationProposal,
    Session,
    SessionStatus,
)
from app.core.planner import Planner
from app.core.remediation_engine import RemediationEngine
from app.core.safety import SafetyValidator
from app.core.verification_engine import VerificationEngine
from app.knowledge.categories import get_category_spec
from app.llm.provider import LLMProvider, get_provider

logger = get_logger(__name__)


@dataclass
class AgentStep:
    """One user-facing step in the agent's reasoning trace."""

    kind: str  # "plan" | "diagnostic" | "analysis" | "recommendation"
    message: str
    tool: str | None = None
    ok: bool | None = None


@dataclass
class AgentResult:
    session: Session
    steps: list[AgentStep] = field(default_factory=list)


ProgressCallback = Callable[[AgentStep], None]


class Agent:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        history: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.max_steps = settings.max_agent_steps
        self.max_attempts = settings.max_remediation_attempts
        self.provider = provider or get_provider()
        self.safety = SafetyValidator()
        self.planner = Planner(self.provider, self.safety)
        self.diagnostics = DiagnosticEngine(self.safety)
        self.remediation = RemediationEngine(self.safety)
        self.verification = VerificationEngine()
        self.history = history

    # --- diagnosis phase ---------------------------------------------------
    def diagnose(
        self,
        problem: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> AgentResult:
        """Plan, gather evidence (bounded), analyze, and recommend fixes."""
        session = Session(problem=problem, status=SessionStatus.DIAGNOSING)
        steps: list[AgentStep] = []

        def emit(step: AgentStep) -> None:
            steps.append(step)
            if progress:
                progress(step)

        # 1. Plan
        plan = self.planner.plan(problem)
        session.plan = plan
        emit(AgentStep("plan", plan.rationale))

        # 2. Gather evidence, bounded by max_steps.
        planned = plan.diagnostic_tools[: self.max_steps]
        results: dict[str, Any] = {}
        for i, tool in enumerate(planned):
            self.safety.check_agent_step(i)
            result = self.diagnostics.run([tool])[tool]
            results[tool] = result
            emit(AgentStep(
                "diagnostic",
                _diagnostic_message(tool, result),
                tool=tool,
                ok=bool(result.get("success")),
            ))
        session.diagnostics = results

        # 3. Reason / analyze evidence into a diagnosis.
        diagnosis = self.provider.analyze(problem, plan.category, results)
        session.diagnosis = diagnosis
        session.status = SessionStatus.DIAGNOSED
        emit(AgentStep("analysis", diagnosis.summary))

        # 4. Recommend remediations (whitelisted, awaiting approval).
        proposals = self.remediation.propose(diagnosis)
        session.proposals = proposals
        if proposals:
            session.status = SessionStatus.AWAITING_APPROVAL
            emit(AgentStep(
                "recommendation",
                f"Recommended fix: {proposals[0].title} ({proposals[0].risk_level.value} risk).",
                tool=proposals[0].tool,
            ))
        else:
            emit(AgentStep(
                "recommendation",
                "No automatic fix is available for this problem; manual steps may be needed.",
            ))

        self._save(session)
        return AgentResult(session=session, steps=steps)

    # --- remediation + verification phase ---------------------------------
    def remediate_and_verify(
        self,
        session: Session,
        proposal: RemediationProposal,
        *,
        approved: bool,
        arguments: dict[str, Any] | None = None,
    ) -> Session:
        """Execute an approved fix and verify whether it helped.

        Approval is mandatory and enforced by the safety layer.
        """
        if len(session.remediations) >= self.max_attempts:
            self.safety.check_remediation_attempt(len(session.remediations))

        session.status = SessionStatus.REMEDIATING
        before = session.diagnostics
        outcome = self.remediation.execute(
            proposal, approved=approved, arguments=arguments
        )
        session.remediations.append(outcome)

        # Verify regardless of whether the tool reported success.
        session.status = SessionStatus.VERIFYING
        category = session.diagnosis.category if session.diagnosis else Category.UNKNOWN
        spec = get_category_spec(category)
        verify_tools = (
            proposal.verification_tools
            or (list(spec.verification_tools) if spec else [])
        )
        verification = self.verification.run(category, verify_tools, before)
        session.verification = verification

        if verification.improved:
            session.status = SessionStatus.RESOLVED
            session.final_outcome = "Fix completed. " + verification.summary
        else:
            session.status = SessionStatus.UNRESOLVED
            session.final_outcome = (
                "The recommended fix did not resolve the issue. " + verification.summary
            )
        self._save(session)
        return session

    def next_proposal(self, session: Session) -> RemediationProposal | None:
        """Return the next untried remediation proposal, if any."""
        tried = {o.tool for o in session.remediations}
        for p in session.proposals:
            if p.tool not in tried:
                return p
        return None

    def _save(self, session: Session) -> None:
        if self.history is not None:
            try:
                self.history.save_session(session)
            except Exception as exc:  # noqa: BLE001 - persistence must not break flow
                logger.warning(
                    "history save failed",
                    extra={"component": "agent", "event": "save_fail",
                           "status": str(exc)},
                )


def _diagnostic_message(tool: str, result: dict[str, Any]) -> str:
    label = tool.replace("get_", "").replace("_", " ")
    if not result.get("success"):
        err = result.get("error") or {}
        if err.get("type") == "UnsupportedPlatform":
            return f"{label}: not available on this platform"
        return f"{label}: could not be collected ({err.get('type', 'error')})"
    return f"{label}: collected"
