"""Main application window.

Wires the screens together and drives the agent through background workers so
the UI never freezes. All remediation goes through the standard approval gate.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.agent import Agent
from app.core.history import HistoryStore
from app.core.models import RemediationProposal, Session
from app.gui.theme import STYLESHEET
from app.gui.views.diagnosis import DiagnosisView
from app.gui.views.history import HistoryView
from app.gui.views.home import HomeView
from app.gui.views.progress import ProgressView
from app.gui.views.settings import SettingsView
from app.gui.views.verification import VerificationView
from app.gui.workers import DiagnoseWorker, RemediateWorker

_HOME, _PROGRESS, _DIAGNOSIS, _VERIFY, _HISTORY, _SETTINGS = range(6)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WinFix AI")
        self.resize(980, 720)
        self.setStyleSheet(STYLESHEET)

        self._history = HistoryStore()
        self._agent = Agent(history=self._history)
        self._session: Session | None = None
        self._worker = None

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._nav_bar())

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Build views
        self.home = HomeView()
        self.progress = ProgressView()
        self.diagnosis = DiagnosisView()
        self.verification = VerificationView()
        self.history = HistoryView(self._history)
        self.settings = SettingsView()
        for v in (self.home, self.progress, self.diagnosis, self.verification,
                  self.history, self.settings):
            self.stack.addWidget(v)

        # Wire signals
        self.home.diagnose_requested.connect(self._start_diagnosis)
        self.home.open_history.connect(self._show_history)
        self.diagnosis.approve.connect(self._start_remediation)
        self.diagnosis.cancel.connect(lambda: self.stack.setCurrentIndex(_HOME))
        self.diagnosis.back.connect(lambda: self.stack.setCurrentIndex(_HOME))
        self.verification.done.connect(lambda: self.stack.setCurrentIndex(_HOME))
        self.verification.retry.connect(self._retry_remediation)
        self.history.back.connect(lambda: self.stack.setCurrentIndex(_HOME))
        self.settings.back.connect(lambda: self.stack.setCurrentIndex(_HOME))

        self.stack.setCurrentIndex(_HOME)

    def _nav_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 10, 16, 10)
        home_btn = QPushButton("Home")
        home_btn.clicked.connect(lambda: self.stack.setCurrentIndex(_HOME))
        hist_btn = QPushButton("History")
        hist_btn.clicked.connect(self._show_history)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(lambda: self.stack.setCurrentIndex(_SETTINGS))
        layout.addWidget(home_btn)
        layout.addWidget(hist_btn)
        layout.addStretch(1)
        layout.addWidget(settings_btn)
        return bar

    # --- diagnosis ---------------------------------------------------------
    def _start_diagnosis(self, problem: str) -> None:
        self.progress.reset(problem)
        self.stack.setCurrentIndex(_PROGRESS)
        self._worker = DiagnoseWorker(self._agent, problem)
        self._worker.step.connect(self.progress.add_step)
        self._worker.finished_ok.connect(self._on_diagnosed)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_diagnosed(self, session: Session) -> None:
        self._session = session
        self.diagnosis.show_session(session)
        self.stack.setCurrentIndex(_DIAGNOSIS)

    # --- remediation -------------------------------------------------------
    def _start_remediation(self, proposal: RemediationProposal) -> None:
        if not self._session:
            return
        args = dict(proposal.parameters)
        self.progress.reset(self._session.problem)
        self.progress.set_phase("Applying fix...")
        self.stack.setCurrentIndex(_PROGRESS)
        self._worker = RemediateWorker(self._agent, self._session, proposal, args)
        self._worker.finished_ok.connect(self._on_remediated)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_remediated(self, session: Session) -> None:
        self._session = session
        can_retry = self._agent.next_proposal(session) is not None
        self.verification.show_session(session, can_retry)
        self.stack.setCurrentIndex(_VERIFY)

    def _retry_remediation(self) -> None:
        if not self._session:
            return
        nxt = self._agent.next_proposal(self._session)
        if nxt:
            self._start_remediation(nxt)

    # --- misc --------------------------------------------------------------
    def _show_history(self) -> None:
        self.history.refresh()
        self.stack.setCurrentIndex(_HISTORY)

    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, "WinFix AI", f"Something went wrong:\n{message}")
        self.stack.setCurrentIndex(_HOME)


def main() -> int:  # pragma: no cover - GUI entrypoint
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("WinFix AI")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
