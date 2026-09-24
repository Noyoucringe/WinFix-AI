"""Main application window.

A sidebar rail plus a stacked content area. All agent work runs on background
threads so the UI never freezes, and every remediation passes through the
standard approval gate.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
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
from app.gui.branding import app_icon
from app.gui.theme import STYLESHEET
from app.gui.views.diagnosis import DiagnosisView
from app.gui.views.history import HistoryView
from app.gui.views.home import HomeView
from app.gui.views.progress import ProgressView
from app.gui.views.settings import SettingsView
from app.gui.views.verification import VerificationView
from app.gui.widgets import container, faint, muted
from app.gui.workers import DiagnoseWorker, RemediateWorker

HOME, PROGRESS, DIAGNOSIS, VERIFY, HISTORY, SETTINGS = range(6)

# Nav entries that map directly to a screen.
_NAV = [
    ("Troubleshoot", HOME),
    ("History", HISTORY),
    ("Settings", SETTINGS),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WinFix AI")
        self.resize(1080, 760)
        self.setMinimumSize(900, 620)
        self.setStyleSheet(STYLESHEET)
        self.setWindowIcon(app_icon())

        self._history = HistoryStore()
        self._agent = Agent(history=self._history)
        self._session: Session | None = None
        self._worker = None

        central = QWidget()
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        shell.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        shell.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.home = HomeView()
        self.progress = ProgressView()
        self.diagnosis = DiagnosisView()
        self.verification = VerificationView()
        self.history = HistoryView(self._history)
        self.settings = SettingsView()
        for view in (self.home, self.progress, self.diagnosis,
                     self.verification, self.history, self.settings):
            self.stack.addWidget(view)

        self.home.diagnose_requested.connect(self._start_diagnosis)
        self.diagnosis.approve.connect(self._start_remediation)
        self.diagnosis.cancel.connect(lambda: self._go(HOME))
        self.verification.done.connect(lambda: self._go(HOME))
        self.verification.retry.connect(self._retry_remediation)

        self._go(HOME)

    # --- chrome ------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(224)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(16, 22, 16, 18)
        layout.setSpacing(6)

        brand = container()
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(6, 0, 0, 0)
        brand_row.setSpacing(10)
        mark = muted("W")
        mark.setObjectName("BrandMark")
        mark.setFixedSize(32, 32)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name = muted("WinFix AI")
        name.setObjectName("Brand")
        brand_row.addWidget(mark)
        brand_row.addWidget(name)
        brand_row.addStretch(1)
        layout.addWidget(brand)
        layout.addSpacing(24)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[int, QPushButton] = {}
        for label, index in _NAV:
            btn = QPushButton(label)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=index: self._go(i))
            self._nav_group.addButton(btn)
            layout.addWidget(btn)
            self._nav_buttons[index] = btn

        layout.addStretch(1)

        from app.llm.provider import get_provider

        provider = get_provider()
        mode = "Cloud AI" if provider.name != "local" else "Offline mode"
        layout.addWidget(faint(mode))
        layout.addWidget(faint("Read-only until you approve"))
        return bar

    def _go(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == HISTORY:
            self.history.refresh()
        # Keep the rail selection sensible for screens that have no nav entry.
        highlight = index if index in self._nav_buttons else HOME
        self._nav_buttons[highlight].setChecked(True)

    # --- diagnosis ---------------------------------------------------------
    def _start_diagnosis(self, problem: str) -> None:
        self.progress.reset(problem)
        self._go(PROGRESS)
        self._worker = DiagnoseWorker(self._agent, problem)
        self._worker.step.connect(self.progress.add_step)
        self._worker.finished_ok.connect(self._on_diagnosed)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_diagnosed(self, session: Session) -> None:
        self._session = session
        self.diagnosis.show_session(session)
        self._go(DIAGNOSIS)

    # --- remediation -------------------------------------------------------
    def _start_remediation(self, proposal: RemediationProposal) -> None:
        if not self._session:
            return
        self.progress.reset(self._session.problem)
        self.progress.set_phase("Applying fix...")
        self._go(PROGRESS)
        self._worker = RemediateWorker(
            self._agent, self._session, proposal, dict(proposal.parameters)
        )
        self._worker.finished_ok.connect(self._on_remediated)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_remediated(self, session: Session) -> None:
        self._session = session
        can_retry = self._agent.next_proposal(session) is not None
        self.verification.show_session(session, can_retry)
        self._go(VERIFY)

    def _retry_remediation(self) -> None:
        if not self._session:
            return
        nxt = self._agent.next_proposal(self._session)
        if nxt:
            self._start_remediation(nxt)

    # --- errors ------------------------------------------------------------
    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, "WinFix AI", f"Something went wrong:\n{message}")
        self._go(HOME)


def main() -> int:  # pragma: no cover - GUI entrypoint
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("WinFix AI")
    app.setOrganizationName("WinFix")
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
