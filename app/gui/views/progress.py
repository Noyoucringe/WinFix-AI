"""Progress screen: live feedback while diagnostics or a fix are running."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from app.core.agent import AgentStep
from app.gui.widgets import (
    Card,
    body,
    container,
    eyebrow,
    faint,
    muted,
    row,
    status_dot,
)

_PHASES = ["Understanding", "Diagnosing", "Analyzing", "Recommending"]


class ProgressView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(56, 48, 56, 40)
        root.setSpacing(0)

        self.eyebrow = eyebrow("WORKING")
        root.addWidget(self.eyebrow)
        root.addSpacing(10)

        self.phase = body("Understanding your problem...")
        self.phase.setObjectName("Title")
        root.addWidget(self.phase)
        root.addSpacing(6)

        self.problem = muted("")
        root.addWidget(self.problem)
        root.addSpacing(22)

        self.card = Card(spacing=4)
        root.addWidget(self.card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._steps_host = container()
        self._steps = QVBoxLayout(self._steps_host)
        self._steps.setContentsMargins(0, 0, 0, 0)
        self._steps.setSpacing(2)
        self._steps.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._steps_host)
        self.card.add(scroll)

        root.addStretch(1)
        root.addWidget(faint("Read-only diagnostics — nothing is changed yet."))

    def reset(self, problem: str) -> None:
        while self._steps.count():
            item = self._steps.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.problem.setText(problem)
        self.set_phase("Understanding your problem...")

    def set_phase(self, text: str) -> None:
        self.phase.setText(text)

    def add_step(self, step: AgentStep) -> None:
        if step.kind == "plan":
            self.set_phase("Running diagnostics...")
            self._add(step.message, None)
        elif step.kind == "diagnostic":
            self._add(step.message.capitalize(), step.ok)
        elif step.kind == "analysis":
            self.set_phase("Analyzing evidence...")
            self._add(step.message, True)
        elif step.kind == "recommendation":
            self._add(step.message, True)

    def _add(self, text: str, ok: bool | None) -> None:
        label = muted(text)
        self._steps.addWidget(row(status_dot(ok), label, spacing=8))
