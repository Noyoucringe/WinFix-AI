"""History screen: past troubleshooting sessions."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.history import HistoryStore
from app.gui.widgets import title_label


class HistoryView(QWidget):
    back = Signal()

    def __init__(self, history: HistoryStore) -> None:
        super().__init__()
        self._history = history
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(title_label("History"))
        header.addStretch(1)
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(self.back.emit)
        header.addWidget(back_btn)
        root.addLayout(header)

        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        body.addWidget(self.list, 1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        body.addWidget(self.detail, 2)
        root.addLayout(body, 1)

    def refresh(self) -> None:
        self.list.clear()
        for row in self._history.list_sessions():
            date = (row.get("created_at") or "")[:10]
            label = f"{date}  •  {row.get('problem', '')[:40]}"
            item = QListWidgetItem(label)
            item.setData(256, row.get("id"))
            self.list.addItem(item)
        if self.list.count() == 0:
            self.detail.setPlainText("No sessions yet.")

    def _on_select(self, current: QListWidgetItem | None) -> None:
        if not current:
            return
        session_id = current.data(256)
        payload = self._history.get_session(session_id)
        if not payload:
            return
        self.detail.setPlainText(self._format(payload))

    def _format(self, p: dict) -> str:
        lines = [
            f"Problem:   {p.get('problem')}",
            f"Status:    {p.get('status')}",
            f"Outcome:   {p.get('final_outcome')}",
            "",
        ]
        diag = p.get("diagnosis") or {}
        if diag:
            lines.append(f"Diagnosis: {diag.get('summary')}")
            for c in diag.get("possible_causes", []):
                lines.append(f"  • {c.get('cause')} ({c.get('confidence')})")
                for e in c.get("evidence", []):
                    lines.append(f"      – {e}")
            lines.append("")
        for r in p.get("remediations", []):
            lines.append(f"Remediation: {r.get('tool')} "
                         f"(approved={r.get('approved')}, success={r.get('success')})")
        ver = p.get("verification")
        if ver:
            lines.append("")
            lines.append(f"Verification: {'improved' if ver.get('improved') else 'no change'}")
            for m in ver.get("metrics", []):
                lines.append(f"  • {m}")
        return "\n".join(lines)
