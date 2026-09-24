"""Diagnosis + fix-approval screen."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import RemediationProposal, Session
from app.gui.theme import RISK_COLORS
from app.gui.widgets import Card, hline, muted, section_header, title_label


class DiagnosisView(QWidget):
    approve = Signal(object)   # RemediationProposal
    cancel = Signal()
    back = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._proposal: RemediationProposal | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        self.body = QVBoxLayout(container)
        self.body.setSpacing(16)
        self.body.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
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

        self.body.addWidget(title_label("Diagnosis"))
        self.body.addWidget(muted(f"Problem: {session.problem}"))

        # Diagnosis summary
        summary_card = Card()
        summary_card.add(section_header("What we found"))
        summary_card.add(muted(diag.summary if diag else "No diagnosis available."))
        source = (diag.analysis_source if diag else "local").upper()
        summary_card.add(muted(f"Analysis source: {source}"))
        self.body.addWidget(summary_card)

        # Evidence / causes
        if diag and diag.possible_causes:
            causes_card = Card()
            causes_card.add(section_header("Possible causes"))
            for c in diag.possible_causes:
                causes_card.add(QLabel(
                    f"• {c.cause}  ({c.likelihood_word}, confidence {c.confidence:.0%})"
                ))
                for e in c.evidence:
                    causes_card.add(muted(f"     – {e}"))
            self.body.addWidget(causes_card)

        # Recommended fix / approval
        if session.proposals:
            self._proposal = session.proposals[0]
            self.body.addWidget(self._approval_card(self._proposal))
        else:
            no_fix = Card()
            no_fix.add(section_header("No automatic fix available"))
            no_fix.add(muted(
                "WinFix did not find a safe, whitelisted automatic fix for this "
                "problem. Review the evidence above; manual steps may be needed."
            ))
            self.body.addWidget(no_fix)

        back_btn = QPushButton("Back to Home")
        back_btn.clicked.connect(self.back.emit)
        self.body.addWidget(back_btn)
        self.body.addStretch(1)

    def _approval_card(self, proposal: RemediationProposal) -> Card:
        card = Card()
        card.add(section_header("Recommended fix"))
        card.add(QLabel(proposal.title))
        card.add(muted(f"Why: {proposal.reason}"))

        risk = proposal.risk_level.value
        color = RISK_COLORS.get(risk, "#f59e0b")
        risk_label = QLabel(f"Risk: {risk.upper()}")
        risk_label.setStyleSheet(f"color:{color}; font-weight:700;")
        card.add(risk_label)
        if proposal.consequences:
            card.add(muted(proposal.consequences))
        if proposal.requires_admin:
            card.add(muted("Requires administrator privileges."))

        card.add(hline())
        buttons = QHBoxLayout()
        approve_btn = QPushButton("Approve Fix")
        approve_btn.setObjectName("Primary")
        if risk == "high":
            approve_btn.setText("Approve High-Risk Fix")
            approve_btn.setObjectName("Danger")
        approve_btn.clicked.connect(self._on_approve)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.cancel.emit)
        buttons.addWidget(cancel_btn)
        buttons.addStretch(1)
        buttons.addWidget(approve_btn)
        wrapper = QWidget()
        wrapper.setLayout(buttons)
        card.add(wrapper)
        return card

    def _on_approve(self) -> None:
        if not self._proposal:
            return
        # High-risk actions require a stronger confirmation.
        if self._proposal.risk_level.value == "high":
            text, ok = QInputDialog.getText(
                self, "Confirm high-risk fix",
                "This action is higher risk and may require a reboot.\n"
                "Type APPROVE to continue:",
            )
            if not ok or text.strip().upper() != "APPROVE":
                return
        self.approve.emit(self._proposal)
