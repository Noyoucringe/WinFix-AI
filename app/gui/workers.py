"""Background workers so the GUI never blocks on diagnostics or fixes.

All agent work runs on a ``QThread``; the UI is updated only via signals.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal

from app.core.agent import Agent
from app.core.models import RemediationProposal, Session


class DiagnoseWorker(QThread):
    """Runs the agent's diagnosis phase, streaming reasoning steps."""

    step = Signal(object)          # AgentStep
    finished_ok = Signal(object)   # Session
    failed = Signal(str)

    def __init__(self, agent: Agent, problem: str) -> None:
        super().__init__()
        self._agent = agent
        self._problem = problem

    def run(self) -> None:  # pragma: no cover - requires Qt event loop
        try:
            result = self._agent.diagnose(
                self._problem, progress=lambda s: self.step.emit(s)
            )
            self.finished_ok.emit(result.session)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class RemediateWorker(QThread):
    """Runs an approved remediation and verification."""

    finished_ok = Signal(object)   # Session
    failed = Signal(str)

    def __init__(
        self,
        agent: Agent,
        session: Session,
        proposal: RemediationProposal,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._session = session
        self._proposal = proposal
        self._arguments = arguments or {}

    def run(self) -> None:  # pragma: no cover - requires Qt event loop
        try:
            updated = self._agent.remediate_and_verify(
                self._session, self._proposal, approved=True,
                arguments=self._arguments,
            )
            self.finished_ok.emit(updated)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
