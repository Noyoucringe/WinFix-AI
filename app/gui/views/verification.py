"""Verification / result screen."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import Session
from app.gui.theme import DANGER, DANGER_SOFT, SUCCESS, SUCCESS_SOFT
from app.gui.widgets import (
    Card,
    body,
    container,
    divider,
    eyebrow,
    faint,
    heading,
    muted,
    title_label,
)


def _action_title(session: Session, tool: str) -> str:
    """Human-readable name for an applied remediation tool."""
    for p in session.proposals:
        if p.tool == tool:
            return p.title
    return tool.replace("_", " ").capitalize()


class VerificationView(QWidget):
    done = Signal()
    retry = Signal()

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = container()
        self._layout = QVBoxLayout(host)
        self._layout.setContentsMargins(56, 48, 56, 40)
        self._layout.setSpacing(16)
        scroll.setWidget(host)
        outer.addWidget(scroll)

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def show_session(self, session: Session, can_retry: bool) -> None:
        self._clear()
        v = session.verification
        improved = bool(v and v.improved)
        color = SUCCESS if improved else DANGER
        soft = SUCCESS_SOFT if improved else DANGER_SOFT

        self._layout.addWidget(eyebrow("VERIFICATION"))

        banner = QFrame()
        banner.setObjectName("Banner")
        banner.setStyleSheet(
            f"QFrame#Banner {{ background-color:{soft}; border:1px solid {color};"
            " border-radius:14px; }"
        )
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(22, 20, 22, 20)
        bl.setSpacing(6)
        headline = title_label(
            "Fix completed" if improved else "Fix did not resolve the issue"
        )
        headline.setStyleSheet(f"color:{color}; background:transparent;")
        bl.addWidget(headline)
        bl.addWidget(muted(session.final_outcome or (v.summary if v else "")))
        self._layout.addWidget(banner)

        # What was applied
        if session.remediations:
            last = session.remediations[-1]
            applied = Card(spacing=8)
            applied.add(heading("Action applied"))
            applied.add(body(_action_title(session, last.tool)))
            applied.add(faint(
                f"Approved: {last.approved} · Executed: {last.executed} · "
                f"Reported success: {last.success}"
            ))
            if last.error:
                applied.add(faint(f"Detail: {last.error.get('message', '')}"))
            self._layout.addWidget(applied)

        # Before / after metrics
        if v and v.metrics:
            metrics = Card(spacing=8)
            metrics.add(heading("Before / after"))
            for i, m in enumerate(v.metrics):
                if i:
                    metrics.add(divider())
                metrics.add(muted(m))
            self._layout.addWidget(metrics)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(10)
        if not improved and can_retry:
            retry_btn = QPushButton("Try Another Fix")
            retry_btn.setObjectName("Primary")
            retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            retry_btn.clicked.connect(self.retry.emit)
            actions.addWidget(retry_btn)

        done_btn = QPushButton("Done")
        done_btn.setObjectName("Ghost" if (not improved and can_retry) else "Primary")
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.clicked.connect(self.done.emit)
        actions.addWidget(done_btn)
        actions.addStretch(1)

        self._layout.addWidget(container(actions))
        self._layout.addStretch(1)
