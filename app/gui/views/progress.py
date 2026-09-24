"""Progress screen: live diagnostic execution feedback."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.agent import AgentStep
from app.gui.widgets import muted, section_header


class ProgressView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 50, 60, 40)
        root.setSpacing(12)

        self.phase = section_header("Understanding your problem...")
        root.addWidget(self.phase)
        root.addWidget(muted("WinFix is gathering evidence with read-only diagnostics."))

        self.steps = QListWidget()
        root.addWidget(self.steps, 1)

    def reset(self, problem: str) -> None:
        self.steps.clear()
        self.phase.setText("Understanding your problem...")

    def set_phase(self, text: str) -> None:
        self.phase.setText(text)

    def add_step(self, step: AgentStep) -> None:
        if step.kind == "plan":
            self.set_phase("Running diagnostics...")
            self._item(f"Plan: {step.message}")
        elif step.kind == "diagnostic":
            mark = "OK" if step.ok else "—"
            self._item(f"[{mark}] {step.message}")
        elif step.kind == "analysis":
            self.set_phase("Analyzing evidence...")
            self._item(f"Analysis: {step.message}")
        elif step.kind == "recommendation":
            self._item(f"Recommendation: {step.message}")

    def _item(self, text: str) -> None:
        self.steps.addItem(QListWidgetItem(text))
        self.steps.scrollToBottom()
