"""Verification / result screen."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from app.core.models import Session
from app.gui.theme import DANGER, SUCCESS
from app.gui.widgets import Card, muted, section_header, title_label


class VerificationView(QWidget):
    done = Signal()
    retry = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(60, 50, 60, 40)
        self._layout.setSpacing(16)

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

        self._layout.addWidget(title_label(
            "Fix completed" if improved else "Fix did not resolve the issue"
        ))

        card = Card()
        header = section_header("Result")
        header.setStyleSheet(f"color:{SUCCESS if improved else DANGER};")
        card.add(header)
        card.add(muted(session.final_outcome or (v.summary if v else "")))
        if v and v.metrics:
            card.add(section_header("Before / after"))
            for m in v.metrics:
                card.add(muted(f"• {m}"))
        self._layout.addWidget(card)

        if not improved and can_retry:
            retry_btn = QPushButton("Try Another Fix")
            retry_btn.setObjectName("Primary")
            retry_btn.clicked.connect(self.retry.emit)
            self._layout.addWidget(retry_btn)

        done_btn = QPushButton("Done")
        done_btn.clicked.connect(self.done.emit)
        self._layout.addWidget(done_btn)
        self._layout.addStretch(1)
