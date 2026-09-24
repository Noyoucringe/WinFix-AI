"""Home screen: describe a problem and start troubleshooting."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui.widgets import muted, section_header, title_label

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
    open_history = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 50, 60, 40)
        root.setSpacing(14)

        root.addWidget(title_label("WinFix AI"))
        root.addWidget(muted("What can we help you fix?"))
        root.addSpacing(10)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("My laptop is very slow...")
        self.input.setFixedHeight(120)
        root.addWidget(self.input)

        buttons = QHBoxLayout()
        self.diagnose_btn = QPushButton("Diagnose Problem")
        self.diagnose_btn.setObjectName("Primary")
        self.diagnose_btn.clicked.connect(self._on_diagnose)
        history_btn = QPushButton("View History")
        history_btn.clicked.connect(self.open_history.emit)
        buttons.addWidget(self.diagnose_btn)
        buttons.addWidget(history_btn)
        buttons.addStretch(1)
        root.addLayout(buttons)

        root.addSpacing(16)
        root.addWidget(section_header("Common problems"))
        chips = QHBoxLayout()
        chips.setSpacing(8)
        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        for i, example in enumerate(_EXAMPLES):
            btn = QPushButton(example)
            btn.clicked.connect(lambda _=False, e=example: self._use_example(e))
            (col1 if i % 2 == 0 else col2).addWidget(btn)
        chips.addLayout(col1)
        chips.addLayout(col2)
        root.addLayout(chips)
        root.addStretch(1)

    def _use_example(self, text: str) -> None:
        self.input.setPlainText(text)

    def _on_diagnose(self) -> None:
        problem = self.input.toPlainText().strip()
        if problem:
            self.diagnose_requested.emit(problem)
