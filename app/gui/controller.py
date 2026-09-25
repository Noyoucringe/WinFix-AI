"""Connects the troubleshooting agent to the UI.

The agent runs on worker threads; its structured events are re-emitted as Qt
signals, which Qt delivers on the UI thread. The UI calls ``apply`` only from
the approval dialog's "Apply fix" button — the agent and safety layer then
enforce that approval again before anything runs.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from app.core.agent import Agent, AgentEvent
from app.core.history import HistoryStore
from app.core.logging_setup import get_logger
from app.core.models import RemediationProposal, Session
from app.core.user_settings import get_store
from app.gui.workers import run_async
from app.llm.provider import get_provider

logger = get_logger(__name__)


class TroubleshootController(QObject):
    event = Signal(object)        # AgentEvent, delivered on the UI thread
    state_changed = Signal(str)   # idle | investigating | diagnosed | applying | result
    failed = Signal(str, str)     # user message, technical detail
    finished = Signal(object)     # Session, when a phase completes

    def __init__(self, history: HistoryStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.history = history
        self.session: Session | None = None
        self.state = "idle"
        self._agent: Agent | None = None
        self._cancel: threading.Event | None = None
        self.pending_proposal: RemediationProposal | None = None
        self.demo = None  # set by demo mode

    # --- helpers ----------------------------------------------------------
    def _set_state(self, state: str) -> None:
        self.state = state
        self.state_changed.emit(state)

    def _emit(self, event: AgentEvent) -> None:
        self.event.emit(event)  # called from worker threads; queued to the UI

    def _on_error(self, message: str, detail: str) -> None:
        logger.error("troubleshooting step failed",
                     extra={"component": "controller", "status": message[:200]})
        self._set_state("error")
        self.failed.emit(message, detail)

    @property
    def busy(self) -> bool:
        return self.state in ("investigating", "applying")

    # --- actions ------------------------------------------------------------
    def start(self, problem: str) -> bool:
        problem = problem.strip()
        if not problem or self.busy:
            return False
        settings = get_store().load()
        self._agent = Agent(provider=get_provider(settings), history=self.history,
                            depth=settings.diagnostic_depth,
                            elevate=self.demo is None)  # demo never asks for admin
        if self.demo is not None:
            self.demo.prepare(problem)
        self._cancel = threading.Event()
        self.session = Session(problem=problem)
        self.pending_proposal = None
        self._set_state("investigating")
        agent, cancel, session = self._agent, self._cancel, self.session
        run_async(lambda: agent.diagnose(problem, events=self._emit, cancel=cancel,
                                         session=session).session,
                  self._on_diagnosed, self._on_error)
        return True

    def _on_diagnosed(self, session: Session) -> None:
        self.session = session
        self._set_state("cancelled" if session.status.value == "cancelled" else "diagnosed")
        self.finished.emit(session)

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

    def rerun(self) -> bool:
        if self.session is None:
            return False
        return self.start(self.session.problem)

    def decline(self) -> None:
        if self.session is not None and self._agent is not None:
            self._agent.decline(self.session)
        self._set_state("idle")

    def apply(self, proposal: RemediationProposal) -> None:
        """Run an approved fix. Call only after the user pressed 'Apply fix'."""
        if self.session is None or self._agent is None or self.busy:
            return
        self.pending_proposal = proposal
        self._set_state("applying")
        agent, session = self._agent, self.session
        run_async(lambda: agent.remediate_and_verify(session, proposal, approved=True,
                                                     events=self._emit),
                  self._on_verified, self._on_error)

    def _on_verified(self, session: Session) -> None:
        self.session = session
        self._set_state("result")
        self.finished.emit(session)

    def continue_investigation(self) -> None:
        if self.session is None or self._agent is None or self.busy:
            return
        self._cancel = threading.Event()
        self._set_state("investigating")
        agent, session, cancel = self._agent, self.session, self._cancel
        run_async(lambda: agent.continue_investigation(session, events=self._emit,
                                                       cancel=cancel),
                  self._on_diagnosed, self._on_error)

    def stop(self) -> None:
        if self.session is not None and self._agent is not None:
            self._agent.stop(self.session)
        self._set_state("idle")

    def max_attempts(self) -> int:
        return self._agent.max_attempts if self._agent else 3
