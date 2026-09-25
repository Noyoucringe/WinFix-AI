"""The WinFix troubleshooting agent.

    understand → plan → run read-only checks → analyze evidence → recommend
    → (user approval) → apply one whitelisted fix → re-measure → report

Bounded by design: at most ``MAX_AGENT_STEPS`` diagnostic tool calls per
session and ``MAX_REMEDIATION_ATTEMPTS`` fixes. Tool choices from any LLM are
validated by the safety layer before they run. Progress is reported as
structured events so the UI can update live, and a session can be cancelled
between checks.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.diagnostic_engine import DiagnosticEngine
from app.core.logging_setup import get_logger
from app.core.models import (
    CheckRecord,
    Level,
    RemediationProposal,
    Session,
    SessionResult,
    SessionStatus,
    now_utc,
)
from app.core.planner import Planner
from app.core.platform_utils import IS_WINDOWS, is_admin
from app.core.remediation_engine import RemediationEngine
from app.core.safety import SafetyError, SafetyValidator
from app.core.verification_engine import VerificationEngine
from app.knowledge import checks as check_catalog
from app.knowledge.categories import get_category_spec
from app.knowledge.remediations import fix_info
from app.llm.provider import MAX_FOLLOW_UPS, LLMProvider, get_provider

# With AI, checks kept free for the model's own follow-up rounds.
AI_FOLLOW_UP_BUDGET = 4
MAX_AI_ROUNDS = 3

logger = get_logger(__name__)


@dataclass
class AgentEvent:
    """A structured progress event for the UI."""

    kind: str  # plan | check_started | check_finished | analyzing | diagnosed |
    #            fix_started | fix_step | fix_finished | verifying | verify_progress |
    #            verified | cancelled | investigating
    session: Session
    tool: str | None = None
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentStep:
    """Concise user-facing reasoning (used by the CLI and API)."""

    kind: str
    message: str
    tool: str | None = None
    ok: bool | None = None


@dataclass
class AgentResult:
    session: Session
    steps: list[AgentStep] = field(default_factory=list)


EventCallback = Callable[[AgentEvent], None]


class Cancelled(Exception):
    pass


class Agent:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        history: Any | None = None,
        *,
        settle_seconds: float | None = None,
        depth: str | None = None,
        elevate: bool = True,
    ) -> None:
        self.provider = provider or get_provider()
        self.safety = SafetyValidator()
        self.planner = Planner(self.provider, self.safety)
        self.diagnostics = DiagnosticEngine(self.safety)
        self.remediation = RemediationEngine(self.safety)
        self.verification = VerificationEngine()
        self.history = history
        self.settle_seconds = settle_seconds
        self.depth = depth or "standard"
        self.elevate = elevate

    # The safety validator is the single source of truth for the bounds.
    @property
    def max_steps(self) -> int:
        return self.safety.max_agent_steps

    @max_steps.setter
    def max_steps(self, value: int) -> None:
        self.safety.max_agent_steps = value

    @property
    def max_attempts(self) -> int:
        return self.safety.max_remediation_attempts

    @max_attempts.setter
    def max_attempts(self, value: int) -> None:
        self.safety.max_remediation_attempts = value

    # ------------------------------------------------------------------ diagnose
    def diagnose(
        self,
        problem: str,
        *,
        progress: Callable[[AgentStep], None] | None = None,
        events: EventCallback | None = None,
        cancel: threading.Event | None = None,
        session: Session | None = None,
    ) -> AgentResult:
        session = session or Session(problem=problem)
        session.status = SessionStatus.DIAGNOSING
        steps: list[AgentStep] = []

        def step(kind: str, message: str, tool: str | None = None, ok: bool | None = None):
            s = AgentStep(kind, message, tool, ok)
            steps.append(s)
            if progress:
                progress(s)

        def emit(kind: str, **kw):
            if events:
                events(AgentEvent(kind, session, **kw))

        if not session.timeline:
            session.add_event("started", "Session started")

        emit("understanding")
        plan = self.planner.plan(problem, self.depth,
                                 max_initial=max(1, self.max_steps - AI_FOLLOW_UP_BUDGET))
        session.plan = plan
        session.checks = [self._record(t) for t in plan.diagnostic_tools[: self.max_steps]]
        if plan.planned_by == "ai":
            session.add_event("ai", "AI read your description", plan.understood)
        step("plan", plan.rationale)
        emit("plan", message=plan.rationale)

        try:
            self._run_checks(session, [c.tool for c in session.checks], cancel, emit, step)
            # Autonomous investigation: with AI, the model decides after each round
            # whether it needs more evidence (bounded by the step limit).
            rounds = MAX_AI_ROUNDS if plan.planned_by == "ai" else 1
            for _ in range(rounds):
                follow_ups = self._follow_up_tools(session)
                reasoning = getattr(self.provider, "last_reasoning", "")
                if reasoning:
                    session.add_event("ai", "AI: " + reasoning)
                    step("reasoning", reasoning)
                    emit("plan", message=reasoning)
                if not follow_ups:
                    break
                session.checks.extend(self._record(t) for t in follow_ups)
                emit("plan", message="Additional checks", data={"follow_up": follow_ups})
                self._run_checks(session, follow_ups, cancel, emit, step)
        except Cancelled:
            return AgentResult(self._cancel(session, emit), steps)

        completed = sum(1 for c in session.checks if c.status == "completed")
        session.add_event("checks", f"{completed} checks completed")
        emit("analyzing")
        self._analyze(session)
        diagnosis = session.diagnosis
        step("analysis", diagnosis.summary)
        session.add_event("diagnosis", f"Diagnosis: {session.short_diagnosis().lower()}",
                          diagnosis.headline)

        self._recommend(session, exclude=set())
        if session.proposals:
            top = session.proposals[0]
            step("recommendation",
                 f"Recommended fix: {top.title} ({top.risk_level.value} risk).", tool=top.tool)
        else:
            step("recommendation",
                 "No automatic fix is available for this problem; manual steps may be needed.")
        emit("diagnosed")
        self._save(session)
        return AgentResult(session, steps)

    def _record(self, tool: str) -> CheckRecord:
        info = check_catalog.info(tool)
        return CheckRecord(tool=tool, label=info.label, summary=info.running,
                           source=info.source)

    def _run_checks(self, session: Session, tools: list[str], cancel, emit, step) -> None:
        for tool in tools:
            record = next(c for c in session.checks if c.tool == tool and c.status == "queued")
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            index = len(session.diagnostics)
            self.safety.check_agent_step(index)  # hard bound on tool calls
            record.status = "running"
            emit("check_started", tool=tool)
            result = self.diagnostics.run([tool])[tool]
            session.diagnostics[tool] = result
            record.status = "completed" if result.get("success") else "failed"
            record.summary = check_catalog.summarize(tool, result)
            record.duration_ms = result.get("duration_ms")
            if not result.get("success"):
                record.error = str((result.get("error") or {}).get("message", ""))[:300]
            step("diagnostic", f"{record.label}: {record.summary}", tool=tool,
                 ok=bool(result.get("success")))
            emit("check_finished", tool=tool, data={"record": record})

    def _follow_up_tools(self, session: Session) -> list[str]:
        """Extra read-only checks chosen from the evidence so far (bounded)."""
        budget = self.max_steps - len(session.diagnostics)
        if budget <= 0:
            if hasattr(self.provider, "last_reasoning"):
                self.provider.last_reasoning = ""
            return []
        requested = self.provider.follow_up_tools(session, self.remaining_candidates(session))
        accepted: list[str] = []
        for name in requested:
            try:
                self.safety.validate_tool_selection(name)
            except SafetyError as exc:
                session.add_event("rejected", "Rejected a tool request", str(exc)[:200])
                logger.warning("rejected follow-up tool",
                               extra={"component": "agent", "event": "reject",
                                      "tool": str(name)[:60]})
                continue
            if not self.safety.is_read_only(name):
                session.add_event("rejected", "Rejected a tool request",
                                  f"'{name}' changes the system; only read-only checks "
                                  "may be requested")
                continue
            if name not in session.diagnostics and name not in accepted:
                accepted.append(name)
        return accepted[: min(budget, MAX_FOLLOW_UPS)]

    def remaining_candidates(self, session: Session) -> list[str]:
        return [t for t in self.diagnostics.registry.diagnostic_names()
                if t not in session.diagnostics]

    def _analyze(self, session: Session) -> None:
        category = session.plan.category
        diagnosis = self.provider.analyze(session.problem, category, session.diagnostics)
        if getattr(self.provider, "last_transmission", None):
            session.cloud = self.provider.last_transmission
        diagnosis.checks_completed = sum(1 for c in session.checks if c.status == "completed")
        session.diagnosis = diagnosis
        session.status = SessionStatus.DIAGNOSED

    def _recommend(self, session: Session, exclude: set[str]) -> None:
        session.proposals = self.remediation.propose(session.diagnosis, session.diagnostics,
                                                     exclude=exclude)
        if session.proposals:
            session.status = SessionStatus.AWAITING_APPROVAL
            session.result = SessionResult.IN_PROGRESS
            return
        session.finished_at = now_utc()
        if session.diagnosis.level in (Level.OK, Level.INFO) and not session.remediations:
            session.result = SessionResult.NO_ISSUE
            session.final_outcome = session.diagnosis.headline
        else:
            session.result = SessionResult.NOT_RESOLVED
            session.final_outcome = ("WinFix has no further safe automatic fix for this "
                                     "problem. " + " ".join(session.diagnosis.notes)).strip()
        session.status = SessionStatus.DIAGNOSED if not session.remediations \
            else SessionStatus.UNRESOLVED

    def _cancel(self, session: Session, emit) -> Session:
        for record in session.checks:
            if record.status in ("queued", "running"):
                record.status = "cancelled"
                record.summary = "Cancelled"
        session.status = SessionStatus.CANCELLED
        session.result = SessionResult.STOPPED
        session.finished_at = now_utc()
        session.final_outcome = "Troubleshooting was stopped before it finished."
        session.add_event("stopped", "Stopped by you")
        emit("cancelled")
        self._save(session)
        return session

    # ------------------------------------------------------------ user choices
    def decline(self, session: Session) -> Session:
        """The user chose 'Not now' / 'Cancel' on a proposed fix."""
        session.approval_status = "declined"
        session.status = SessionStatus.CANCELLED
        session.result = SessionResult.STOPPED
        session.finished_at = now_utc()
        session.final_outcome = "No changes were made. You chose not to apply the fix."
        session.add_event("declined", "Fix not applied", "You chose not to apply the fix")
        self._save(session)
        return session

    def stop(self, session: Session) -> Session:
        """The user chose 'Stop troubleshooting' after a fix."""
        if session.result == SessionResult.IN_PROGRESS or session.status in (
                SessionStatus.UNRESOLVED, SessionStatus.AWAITING_APPROVAL):
            session.result = SessionResult.STOPPED if not session.verification or \
                not session.verification.improved else SessionResult.RESOLVED
        session.finished_at = session.finished_at or now_utc()
        session.add_event("stopped", "Troubleshooting stopped by you")
        self._save(session)
        return session

    # ------------------------------------------------------------ remediate
    def remediate_and_verify(
        self,
        session: Session,
        proposal: RemediationProposal,
        *,
        approved: bool,
        arguments: dict[str, Any] | None = None,
        events: EventCallback | None = None,
    ) -> Session:
        """Apply one approved fix, then re-measure and report. Approval is enforced."""
        self.safety.check_remediation_attempt(len(session.remediations))
        arguments = dict(proposal.parameters if arguments is None else arguments)
        # Fail closed before touching anything if approval or arguments are invalid.
        self.safety.validate_remediation(proposal.tool, approved=approved, arguments=arguments)

        def emit(kind: str, **kw):
            if events:
                events(AgentEvent(kind, session, **kw))

        info = fix_info(proposal.tool)
        session.approval_status = "approved"
        session.status = SessionStatus.REMEDIATING
        approved_event = session.add_event("approved", "Fix approved by you", proposal.title)
        emit("fix_started", tool=proposal.tool, data={"approved_at": approved_event.at})
        for i, text in enumerate(info.steps):
            emit("fix_step", tool=proposal.tool, message=text, data={"index": i})

        outcome = self.remediation.execute(proposal, approved=approved, arguments=arguments,
                                           runner=self._runner(proposal))
        session.remediations.append(outcome)
        if outcome.success:
            session.add_event("applied", info.title.replace("Restart", "Restarted", 1)
                              if info.title.startswith("Restart") else f"{info.title}: done")
        else:
            message = str((outcome.error or {}).get("message", ""))
            session.add_event("failed", "Fix couldn't be applied", message[:200])
        emit("fix_finished", tool=proposal.tool, data={"outcome": outcome})

        session.status = SessionStatus.VERIFYING
        emit("verifying", tool=proposal.tool,
             data={"pending": self.verification.pending_checks(session, proposal)})
        verification = self.verification.run(
            session, proposal, outcome, settle_seconds=self.settle_seconds,
            progress=lambda tool, result: emit("verify_progress", tool=tool))
        session.verification = verification
        session.verifications.append(verification)
        session.final_outcome = f"{verification.headline} {verification.summary}".strip()

        if verification.improved:
            session.status = SessionStatus.RESOLVED
            session.result = SessionResult.RESOLVED
            session.finished_at = now_utc()
            session.add_event("verified", "Verified: resolved")
        else:
            session.status = SessionStatus.UNRESOLVED
            session.result = SessionResult.NOT_RESOLVED
            session.add_event("verified", "Verified: not resolved",
                              verification.headline)
        emit("verified")
        self._save(session)
        return session

    def _runner(self, proposal: RemediationProposal):
        """Route admin-only fixes through a UAC prompt when not already elevated."""
        from app import demo

        if demo.is_active():  # demo fixes are simulated in-process, never elevated
            return None
        if not (self.elevate and IS_WINDOWS and proposal.requires_admin and not is_admin()):
            return None
        from app.core import elevation

        def run(tool: str, arguments: dict[str, Any]):
            return elevation.run_elevated(tool, arguments), True

        return run

    # ------------------------------------------------------------ continue
    def continue_investigation(
        self,
        session: Session,
        *,
        events: EventCallback | None = None,
        cancel: threading.Event | None = None,
    ) -> Session:
        """After a fix didn't resolve the problem: more checks, then the next fix."""
        if len(session.remediations) >= self.max_attempts:
            raise SafetyError(
                f"Reached the maximum of {self.max_attempts} fixes for one session")

        def emit(kind: str, **kw):
            if events:
                events(AgentEvent(kind, session, **kw))

        # Carry the latest measurements forward so analysis reflects the PC now.
        if session.verification:
            session.diagnostics.update(session.verification.after)
        session.add_event("investigating", "Investigation continued")
        emit("investigating")

        spec = get_category_spec(session.plan.category) if session.plan else None
        extra = [t for t in (spec.thorough_tools if spec else ())
                 if t not in session.diagnostics]
        budget = self.max_steps - len(session.diagnostics)
        extra = extra[: max(0, budget)]
        session.checks.extend(self._record(t) for t in extra)
        emit("plan", message="Additional checks", data={"follow_up": extra})
        try:
            self._run_checks(session, extra, cancel, emit, lambda *a, **k: None)
        except Cancelled:
            return self._cancel(session, emit)

        self._analyze(session)
        session.add_event("diagnosis", "Updated diagnosis", session.diagnosis.headline)
        tried = {r.tool for r in session.remediations}
        self._recommend(session, exclude=tried)
        emit("diagnosed")
        self._save(session)
        return session

    def next_proposal(self, session: Session) -> RemediationProposal | None:
        tried = {o.tool for o in session.remediations}
        return next((p for p in session.proposals if p.tool not in tried), None)

    def _save(self, session: Session) -> None:
        if self.history is None:
            return
        try:
            self.history.save_session(session)
        except Exception as exc:  # noqa: BLE001 - persistence must not break the flow
            logger.error("history save failed",
                         extra={"component": "agent", "event": "save_fail",
                                "status": str(exc)[:200]})
