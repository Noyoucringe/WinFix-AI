"""History screen: past troubleshooting sessions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.history import HistoryStore
from app.gui.widgets import display, eyebrow, muted

_ID_ROLE = Qt.ItemDataRole.UserRole


class HistoryView(QWidget):
    def __init__(self, history: HistoryStore) -> None:
        super().__init__()
        self._history = history
        root = QVBoxLayout(self)
        root.setContentsMargins(56, 48, 56, 40)
        root.setSpacing(0)

        root.addWidget(eyebrow("HISTORY"))
        root.addSpacing(10)
        root.addWidget(display("Past sessions"))
        root.addSpacing(6)
        root.addWidget(muted(
            "Every diagnosis, approval, fix, and verification is recorded locally."
        ))
        root.addSpacing(22)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.list = QListWidget()
        self.list.setMinimumWidth(280)
        self.list.currentItemChanged.connect(self._on_select)
        body.addWidget(self.list, 2)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        body.addWidget(self.detail, 3)
        root.addLayout(body, 1)

    def refresh(self) -> None:
        self.list.clear()
        rows = self._history.list_sessions()
        for r in rows:
            date = (r.get("created_at") or "")[:10]
            status = (r.get("status") or "").replace("_", " ")
            problem = (r.get("problem") or "")[:44]
            item = QListWidgetItem(f"{date}   {problem}\n{status}")
            item.setData(_ID_ROLE, r.get("id"))
            self.list.addItem(item)
        if not rows:
            self.detail.setPlainText(
                "No sessions yet.\n\nRun a diagnosis from the Troubleshoot screen "
                "and it will appear here."
            )
        else:
            self.list.setCurrentRow(0)

    def _on_select(self, current: QListWidgetItem | None) -> None:
        if not current:
            return
        payload = self._history.get_session(current.data(_ID_ROLE))
        if payload:
            self.detail.setPlainText(self._format(payload))

    def _format(self, p: dict) -> str:
        lines = [
            f"Problem:  {p.get('problem')}",
            f"Status:   {p.get('status')}",
            f"Outcome:  {p.get('final_outcome') or '—'}",
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

        diagnostics = p.get("diagnostics") or {}
        if diagnostics:
            lines.append("Diagnostics run:")
            for name, r in diagnostics.items():
                mark = "ok" if r.get("success") else "failed"
                lines.append(f"  [{mark}] {name}")
            lines.append("")

        for r in p.get("remediations", []):
            lines.append(
                f"Remediation: {r.get('tool')} "
                f"(approved={r.get('approved')}, success={r.get('success')})"
            )
        ver = p.get("verification")
        if ver:
            lines.append("")
            lines.append(
                f"Verification: {'improved' if ver.get('improved') else 'no change'}"
            )
            for m in ver.get("metrics", []):
                lines.append(f"  • {m}")
        return "\n".join(lines)
