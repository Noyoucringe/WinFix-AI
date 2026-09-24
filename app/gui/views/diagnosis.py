"""Diagnosis + fix-approval screen."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import RemediationProposal, Session
from app.gui.theme import TEXT_MUTED
from app.gui.widgets import (
    Card,
    ConfidenceBar,
    Pill,
    body,
    container,
    divider,
    eyebrow,
    faint,
    heading,
    muted,
    risk_pill,
    title_label,
)


class DiagnosisView(QWidget):
    approve = Signal(object)   # RemediationProposal
    cancel = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._proposal: RemediationProposal | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = container()
        self.body = QVBoxLayout(host)
        self.body.setContentsMargins(56, 48, 56, 40)
        self.body.setSpacing(16)
        scroll.setWidget(host)
        outer.addWidget(scroll)

    def _clear(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def show_session(self, session: Session) -> None:
        self._clear()
        diag = session.diagnosis

        self.body.addWidget(eyebrow("DIAGNOSIS"))
        self.body.addWidget(title_label("Here's what we found"))
        self.body.addWidget(muted(f"Problem: {session.problem}"))
        self.body.addSpacing(6)

        # --- evidence / causes ---
        if diag and diag.possible_causes:
            causes = Card(spacing=12)
            causes.add(body(diag.summary))
            causes.add(divider())
            causes.add(heading("What the evidence shows"))
            for i, c in enumerate(diag.possible_causes):
                if i:
                    causes.add(divider())
                causes.add(body(c.cause))
                causes.add(ConfidenceBar(c.confidence, c.likelihood_word))
                for e in c.evidence:
                    causes.add(faint(f"— {e}"))
            self.body.addWidget(causes)
        else:
            empty = Card()
            empty.add(heading("No strong signal found"))
            empty.add(muted(
                "The diagnostics ran successfully but did not point clearly to a "
                "single cause. The technical details are saved in this session's "
                "history."
            ))
            self.body.addWidget(empty)

        # --- collected diagnostics summary ---
        ok = sum(1 for r in session.diagnostics.values() if r.get("success"))
        total = len(session.diagnostics)
        source = (diag.analysis_source if diag else "local").upper()
        meta = Card(spacing=8)
        meta.add(heading("Diagnostics collected"))
        meta.add(muted(f"{ok} of {total} diagnostics returned data."))
        meta.add(faint(f"Analysis source: {source}"))
        self.body.addWidget(meta)

        # --- recommended fix / approval gate ---
        if session.proposals:
            self._proposal = session.proposals[0]
            self.body.addWidget(self._approval_card(self._proposal))
        else:
            self._proposal = None
            none_card = Card()
            none_card.add(heading("No automatic fix available"))
            none_card.add(muted(
                "WinFix has no safe, whitelisted automatic fix for this problem. "
                "Review the evidence above — manual steps may be needed."
            ))
            self.body.addWidget(none_card)

        self.body.addStretch(1)

    def _approval_card(self, proposal: RemediationProposal) -> Card:
        card = Card(spacing=12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(heading("Recommended fix"))
        header.addStretch(1)
        header.addWidget(risk_pill(proposal.risk_level.value))
        if proposal.requires_admin:
            header.addWidget(Pill("ADMIN", TEXT_MUTED, "transparent"))
        card.add(container(header))

        card.add(body(proposal.title))
        card.add(muted(proposal.reason))
        if proposal.consequences:
            card.add(faint(proposal.consequences))

        card.add(divider())

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.cancel.emit)

        is_high = proposal.risk_level.value == "high"
        approve_btn = QPushButton(
            "Approve High-Risk Fix" if is_high else "Approve Fix"
        )
        approve_btn.setObjectName("Danger" if is_high else "Primary")
        approve_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        approve_btn.clicked.connect(self._on_approve)

        buttons.addWidget(cancel_btn)
        buttons.addStretch(1)
        buttons.addWidget(approve_btn)
        card.add(container(buttons))

        card.add(faint("Nothing is changed until you approve."))
        return card

    def _on_approve(self) -> None:
        if not self._proposal:
            return
        if self._proposal.risk_level.value == "high":
            text, ok = QInputDialog.getText(
                self, "Confirm high-risk fix",
                "This action is higher risk and may require a reboot.\n"
                "Type APPROVE to continue:",
            )
            if not ok or text.strip().upper() != "APPROVE":
                return
        self.approve.emit(self._proposal)
