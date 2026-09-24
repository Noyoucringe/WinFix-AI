"""Home screen: describe a problem and start troubleshooting."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.widgets import display, eyebrow, faint, muted

_EXAMPLES = [
    "My laptop is very slow.",
    "My Wi-Fi keeps disconnecting.",
    "Windows Update is not working.",
    "My disk is almost full.",
    "Bluetooth isn't working.",
    "My audio isn't working.",
]


class HomeView(QWidget):
    diagnose_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(56, 48, 56, 40)
        root.setSpacing(0)

        root.addWidget(eyebrow("TROUBLESHOOT"))
        root.addSpacing(10)
        root.addWidget(display("What can we help you fix?"))
        root.addSpacing(8)
        root.addWidget(muted(
            "Describe the problem in your own words. WinFix runs read-only "
            "diagnostics first and always asks before changing anything."
        ))
        root.addSpacing(22)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("My laptop is very slow...")
        self.input.setFixedHeight(130)
        root.addWidget(self.input)
        root.addSpacing(16)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.diagnose_btn = QPushButton("Diagnose Problem")
        self.diagnose_btn.setObjectName("Primary")
        self.diagnose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.diagnose_btn.clicked.connect(self._on_diagnose)
        actions.addWidget(self.diagnose_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        root.addSpacing(34)
        root.addWidget(eyebrow("COMMON PROBLEMS"))
        root.addSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, example in enumerate(_EXAMPLES):
            chip = QPushButton(example)
            chip.setObjectName("Chip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, e=example: self._use_example(e))
            grid.addWidget(chip, i // 2, i % 2)
        root.addLayout(grid)

        root.addStretch(1)
        root.addWidget(faint(
            "Diagnostics are read-only. No changes are made without your approval."
        ))

    def _use_example(self, text: str) -> None:
        self.input.setPlainText(text)
        self.input.setFocus()

    def _on_diagnose(self) -> None:
        problem = self.input.toPlainText().strip()
        if problem:
            self.diagnose_requested.emit(problem)
