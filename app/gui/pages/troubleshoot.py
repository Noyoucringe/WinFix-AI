"""Troubleshoot: the live flow from investigation to verified result.

Views (driven by real agent events, never by timers):
start -> investigating -> diagnosis -> recommended fix -> [approval dialog]
-> applying -> verifying -> result (resolved / not resolved / not applied).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from app.core.agent import AgentEvent
from app.core.models import CheckStatus, Level, RemediationProposal, Session, SessionResult
from app.core.platform_utils import is_admin
from app.gui import theme
from app.gui.icons import IconLabel
from app.gui.pages.base import AppContext, Page, clock, header
from app.gui.pages.home import ProblemInput
from app.gui.widgets.composite import (
    Breadcrumb,
    CompareTable,
    DiagnosticRow,
    EvidenceCard,
    Expander,
    FlowGrid,
    Footnote,
    KeyValueTable,
    ListCard,
    NumberBadge,
    Timeline,
)
from app.gui.widgets.core import Button, Card, Divider, Text, font, hbox, vbox
from app.gui.widgets.dialog import ContentDialog
from app.gui.widgets.status import InfoBar, ProgressBar, StatusIcon
from app.knowledge import checks as check_catalog
from app.knowledge.remediations import fix_info
from app.knowledge.troubleshooting import short_label
from app.llm.provider import AI_UNAVAILABLE

_LEVEL_STATE = {Level.OK: "success", Level.INFO: "info", Level.CAUTION: "caution",
                Level.CRITICAL: "critical"}
_RISK_WORD = {"none": "None", "low": "Low", "medium": "Medium", "high": "High"}
_GERUND = {"Restart": "Restarting", "Clear": "Clearing", "Renew": "Renewing",
           "Release": "Releasing", "Reset": "Resetting", "Delete": "Deleting",
           "Empty": "Emptying", "End": "Ending"}


def running_title(title: str) -> str:
    first, _, rest = title.partition(" ")
    return f"{_GERUND.get(first, first)} {rest}".strip()


class ModeTag(QFrame):
    """Makes read-only diagnosis vs. system modification unmistakable."""

    def __init__(self, change: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ModeTag")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 10, 3)
        layout.setSpacing(6)
        token = "caution" if change else "success"
        layout.addWidget(IconLabel("shield" if change else "lock", token, 14))
        text = ("System modification — only after you approve" if change
                else "Read-only diagnosis — nothing on your PC was changed")
        layout.addWidget(Text(text, "caption"))
        p = theme.palette()
        self.setStyleSheet(f"QFrame#ModeTag {{ background: {p.card}; border: 1px solid "
                           f"{p.card_border}; border-radius: 4px; }}")


def raised(card: QWidget) -> QWidget:
    shadow = QGraphicsDropShadowEffect(card)
    shadow.setBlurRadius(16)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(*theme.palette().shadow))
    card.setGraphicsEffect(shadow)
    return card


class TroubleshootPage(Page):
    key = nav_key = "troubleshoot"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.view = ""
        self.rows: dict[str, DiagnosticRow] = {}
        self.error: tuple[str, str] | None = None
        self.notice: str | None = None
        ctx.controller.event.connect(self._on_event)
        ctx.controller.state_changed.connect(self._on_state)
        ctx.controller.failed.connect(self._on_failed)

    # --- routing -------------------------------------------------------------
    @property
    def session(self) -> Session | None:
        return self.ctx.controller.session

    def on_show(self, view: str | None = None, **params) -> None:
        if view:
            self.show_view(view)
            return
        state = self.ctx.controller.state
        mapping = {"investigating": "investigating", "diagnosed": "diagnosis",
                   "applying": "applying", "result": "result"}
        self.show_view(mapping.get(state, "start"))

    def show_view(self, view: str) -> None:
        if view in ("diagnosis", "fix", "result") and self.session is None:
            view = "start"
        if view == "result" and self.session.verification is None:
            view = "diagnosis"
        self.view = view
        self.clear()
        builder = {
            "start": self._start, "investigating": self._investigating,
            "diagnosis": self._diagnosis, "fix": self._fix, "applying": self._applying,
            "verifying": self._verifying, "result": self._result,
        }[view]
        builder()

    def _on_state(self, state: str) -> None:
        if not self.isVisible():
            # The user is elsewhere in the app (or WinFix is in the background).
            self._notify_if_needed(state, force=True)
            return
        if state == "investigating":
            self.show_view("investigating")
        elif state == "diagnosed":
            self.show_view("diagnosis")
        elif state == "result":
            self.show_view("result")
        elif state == "cancelled":
            self.notice = "Troubleshooting was stopped. No changes were made."
            self.show_view("start")
        elif state == "applying":
            self.show_view("applying")
        self._notify_if_needed(state)

    def _notify_if_needed(self, state: str, force: bool = False) -> None:
        """Tell the user about approvals and results they can't already see."""
        if not force and self.window().isActiveWindow():
            return
        session = self.session
        if session is None:
            return
        if state == "diagnosed" and session.proposals and session.diagnosis:
            self.ctx.notify("A fix needs your approval", session.diagnosis.headline)
        elif state == "result" and session.verification:
            self.ctx.notify("Troubleshooting finished", session.verification.headline)

    def _on_failed(self, message: str, detail: str) -> None:
        self.error = (message, detail)
        if self.isVisible():
            self.show_view("start")
        else:
            self.ctx.error("Something went wrong", message, detail)

    def _crumb(self) -> str:
        problem = self.session.problem if self.session else ""
        return f'Troubleshooting · "{problem}"'

    # --- start -----------------------------------------------------------------
    def _start(self) -> None:
        self.add(Text("Troubleshoot", "title_large"))
        self.add(4)
        self.add(Text("Describe the problem and WinFix will investigate it with read-only "
                      "checks.", "body", "secondary", wrap=True))
        self.add(24)
        if self.notice:
            self.add(InfoBar("info", self.notice, closable=True), 16)
            self.notice = None
        if self.error:
            message, detail = self.error
            bar = InfoBar("critical", "Troubleshooting couldn't finish.", message,
                          action="Details")
            bar.action_button.clicked.connect(
                lambda: self.ctx.error("Technical details", message, detail))
            self.add(bar, 16)
            self.error = None
        self.input = ProblemInput(self._submit)
        self.add(self.input)

    def _submit(self, problem: str) -> None:
        if self.ctx.controller.start(problem):
            self.show_view("investigating")

    # --- investigating -------------------------------------------------------------
    def _investigating(self) -> None:
        cancel = Button("Cancel", "Standard")
        cancel.clicked.connect(self._cancel)
        self.add(header("Investigating your PC",
                        "WinFix is collecting evidence to understand what's causing the "
                        "problem.", caption=self._crumb(), actions=[cancel]))
        self.add(24)
        top = QHBoxLayout()
        self.current = Text("Understanding your problem...", "body")
        self.count = Text("", "caption", "secondary")
        top.addWidget(self.current, 1)
        top.addWidget(self.count)
        self.add(top)
        self.add(8)
        self.bar = ProgressBar()
        self.bar.set_value(None)
        self.add(self.bar)
        self.add(16)
        self.list = ListCard()
        self.add(self.list)
        self.add(12)
        self.details = Expander("document", "Technical details",
                                "Data sources, timings and read-only status")
        self.add(self.details)
        self.rows = {}
        session = self.session
        if session and session.checks:
            self._build_rows(session)

    def _cancel(self) -> None:
        self.current.setText("Stopping after the current check...")
        self.ctx.controller.cancel()

    def _build_rows(self, session: Session) -> None:
        for record in session.checks:
            if record.tool in self.rows:
                continue
            info = check_catalog.info(record.tool)
            row = DiagnosticRow(info.icon, record.label, record.summary or info.running)
            self.list.add_row(row)
            self.rows[record.tool] = row
            if record.status != "queued":
                row.set_state(record.status, record.summary)
        self._update_progress(session)

    def _update_progress(self, session: Session) -> None:
        total = len(session.checks)
        done = sum(1 for c in session.checks if c.status in ("completed", "failed"))
        self.count.setText(f"{done} of {total} checks complete")
        self.bar.set_value(done / total if total else None)
        running = next((c for c in session.checks if c.status == "running"), None)
        if running:
            self.current.setText(f"Checking {running.label.lower()}...")
        self._fill_details(session)

    def _fill_details(self, session: Session) -> None:
        layout = self.details.content_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        table = KeyValueTable(label_width=120, style="caption")
        table.add("Session", session.display_id, divider=False)
        table.add("Mode", "Read-only checks — no changes made", divider=False)
        sources = sorted({c.source for c in session.checks if c.source})
        table.add("Sources", ", ".join(sources), divider=False)
        table.add("Started", session.created_at.astimezone().strftime("%I:%M:%S %p")
                  .lstrip("0"), divider=False)
        for c in session.checks:
            if c.duration_ms is not None:
                table.add(c.label, f"{c.status} · {c.duration_ms:.0f} ms · {c.source}",
                          divider=False)
        layout.addWidget(table)

    def _on_event(self, event: AgentEvent) -> None:
        session = event.session
        if self.view == "investigating":
            if event.kind == "plan":
                self._build_rows(session)
            elif event.kind in ("check_started", "check_finished"):
                record = next((c for c in session.checks if c.tool == event.tool), None)
                row = self.rows.get(event.tool)
                if record and row:
                    row.set_state(record.status, record.summary if event.kind ==
                                  "check_finished" else check_catalog.info(record.tool).running)
                self._update_progress(session)
            elif event.kind == "analyzing":
                self.current.setText("Analyzing the evidence...")
                self.bar.set_value(None)
        elif self.view == "applying":
            if event.kind == "fix_step":
                self.timeline.set_step(2, "running", detail=event.message)
            elif event.kind == "fix_finished":
                outcome = event.data.get("outcome")
                self.timeline.set_step(2, "completed" if outcome and outcome.success
                                       else "failed")
            elif event.kind == "verifying":
                self.pending = event.data.get("pending", [])
                self.show_view("verifying")

    # --- diagnosis -------------------------------------------------------------
    def _diagnosis(self) -> None:
        session = self.session
        d = session.diagnosis
        again = Button("Run checks again", "Standard", "refresh")
        again.clicked.connect(self._rerun)
        self.add(header("Diagnosis", caption=self._crumb(), actions=[again]))
        self.add(20)

        state = _LEVEL_STATE[d.level]
        headline = QHBoxLayout()
        headline.setSpacing(12)
        headline.addWidget(StatusIcon(state, 24), 0, Qt.AlignmentFlag.AlignTop)
        when = clock(d.completed_at)
        headline.addLayout(vbox(
            Text(d.headline, "subtitle", wrap=True),
            Text(f"Based on the diagnostics collected from your system · "
                 f"{d.checks_completed} checks completed at {when}", "body", "secondary",
                 wrap=True), spacing=4), 1)
        self.add(headline)
        self.add(12)
        self.add(hbox(ModeTag(change=False), stretch_at=0))
        self.add(16)
        if d.ai_status == "unavailable":
            self.add(InfoBar("info", AI_UNAVAILABLE), 16)
        elif d.ai_status == "cloud":
            items = ", ".join(session.cloud.items) or "measurements and findings"
            self.add(InfoBar("info", "Analyzed with cloud AI.",
                             f"Sent to {session.cloud.endpoint_host}: {items.lower()}."), 16)

        if d.evidence_cards:
            self.add(Text("Evidence", "body_strong"))
            self.add(8)
            grid = FlowGrid(min_width=176)
            grid.set_items([EvidenceCard(c.label, c.icon, c.value, c.detail, c.level.value,
                                         c.status_text, c.progress)
                            for c in d.evidence_cards])
            self.add(grid)
            self.add(28)

        problems = [c for c in d.possible_causes if c.level in (Level.CAUTION,
                                                                Level.CRITICAL)]
        others = [c for c in d.possible_causes if c not in problems]
        shown = (problems + others)[:4]
        if shown:
            self.add(Text("Possible causes" if problems else "Worth knowing", "body_strong"))
            self.add(8)
            causes = ListCard()
            for i, cause in enumerate(shown, 1):
                row = QWidget()
                lay = QHBoxLayout(row)
                lay.setContentsMargins(16, 12, 16, 12)
                lay.setSpacing(16)
                lay.addWidget(NumberBadge(i), 0, Qt.AlignmentFlag.AlignTop)
                lay.addLayout(vbox(Text(cause.cause, "body_strong", wrap=True),
                                   Text(cause.detail, "body", "secondary", wrap=True),
                                   spacing=2), 1)
                causes.add_row(row)
            self.add(causes)
            self.add(20)

        if session.proposals:
            self.add(self._recommendation(session.proposals[0]))
        elif d.level in (Level.OK, Level.INFO):
            done = Button("Done", "Accent")
            done.clicked.connect(self._done)
            self.add(hbox(done, stretch_at=0))
        else:
            card = Card(padding=(20, 18, 20, 18))
            card.add(Text("No automatic fix is available", "body_strong"))
            card.add(Text("WinFix only applies fixes that are safe and predefined. The "
                          "findings above explain what's going on and what you can do.",
                          "body", "secondary", wrap=True))
            done = Button("Done", "Accent")
            done.clicked.connect(self._done)
            diag = Button("View diagnostics", "Standard")
            diag.clicked.connect(lambda: self.ctx.navigate("diagnostics"))
            card.add(hbox(done, diag, stretch_at=1))
            self.add(card)
        for note in d.notes:
            self.add(12)
            self.add(Footnote(note))

    def _recommendation(self, proposal: RemediationProposal) -> QWidget:
        card = Card(padding=(20, 18, 20, 18))
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(IconLabel("troubleshoot", "accent", 20), 0, Qt.AlignmentFlag.AlignTop)
        caption = "Recommended action" if proposal.evidence_backed else "Suggested general step"
        row.addLayout(vbox(Text(caption, "caption", "secondary"),
                           Text(proposal.title, "subtitle"),
                           Text(proposal.summary, "body", wrap=True), spacing=2), 1)
        review = Button("Review fix", "Accent")
        review.clicked.connect(lambda: self.show_view("fix"))
        not_now = Button("Not now", "Standard")
        not_now.clicked.connect(self._decline)
        row.addLayout(hbox(review, not_now), 0)
        card.add(row)
        return raised(card)

    def _rerun(self) -> None:
        if self.ctx.controller.rerun():
            self.show_view("investigating")

    def _decline(self) -> None:
        self.ctx.controller.decline()
        self.ctx.navigate("home")

    def _done(self) -> None:
        self.ctx.controller.stop()
        self.ctx.navigate("home")

    # --- recommended fix -------------------------------------------------------
    def _fix(self) -> None:
        session = self.session
        proposal = session.proposals[0]
        self.add(Text(self._crumb(), "caption", "secondary", wrap=True))
        self.add(4)
        crumb = Breadcrumb(["Diagnosis", "Recommended fix"])
        crumb.navigate.connect(lambda _i: self.show_view("diagnosis"))
        self.add(crumb)
        self.add(20)
        bar = InfoBar("caution" if session.diagnosis.level != Level.OK else "info",
                      "Diagnosis:", session.diagnosis.summary, action="View evidence")
        bar.action_button.setObjectName("Hyperlink")
        bar.action_button.clicked.connect(lambda: self.show_view("diagnosis"))
        self.add(bar, 16)

        card = Card(padding=(24, 22, 24, 22), spacing=0)
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(IconLabel("troubleshoot", "accent", 20), 0, Qt.AlignmentFlag.AlignTop)
        top.addLayout(vbox(hbox(Text("Proposed change", "caption", "secondary"),
                                ModeTag(change=True), stretch_at=1),
                           Text(proposal.title, "subtitle"),
                           Text(proposal.description, "body", wrap=True), spacing=4), 1)
        card.add(top)
        card.body.addSpacing(12)
        table = KeyValueTable(label_width=180)
        risk = QWidget()
        risk_row = QHBoxLayout(risk)
        risk_row.setContentsMargins(0, 0, 0, 0)
        risk_row.setSpacing(6)
        risk_token = {"low": "success", "medium": "caution", "high": "critical"}.get(
            proposal.risk_level.value, "text")
        risk_row.addWidget(IconLabel("shield_check", risk_token, 16))
        risk_row.addWidget(Text(_RISK_WORD[proposal.risk_level.value], "body_strong"))
        note = proposal.risk_note.split("·", 1)[-1].strip()
        risk_row.addWidget(Text(f"· {note}", "body", "secondary", wrap=True), 1)
        table.add("Risk level", risk, divider=False)
        table.add("Expected effect", proposal.expected_effect)
        table.add("What will change", proposal.what_changes)
        table.add("What won't change", proposal.what_unchanged)
        table.add("Permission", "Administrator permission is required." if
                  proposal.requires_admin else "No administrator permission needed.")
        table.add("Time", proposal.estimated_time)
        wrapper = QWidget()
        lay = QHBoxLayout(wrapper)
        lay.setContentsMargins(36, 0, 0, 0)
        lay.addWidget(table)
        card.add(wrapper)
        card.body.addSpacing(12)
        card.add(Divider())
        card.body.addSpacing(16)
        approve = Button("Approve fix", "Accent", "shield" if proposal.requires_admin else None)
        approve.clicked.connect(lambda: self._confirm(proposal))
        cancel = Button("Cancel", "Standard")
        cancel.clicked.connect(lambda: self.show_view("diagnosis"))
        lock = hbox(IconLabel("lock", "text_secondary", 16),
                    Text("Nothing changes on your PC until you approve.", "caption",
                         "secondary"), spacing=6)
        actions = QHBoxLayout()
        actions.addWidget(approve)
        actions.addWidget(cancel)
        actions.addStretch(1)
        actions.addLayout(lock)
        card.add(actions)
        self.add(raised(card))
        self.add(12)

        details = Expander("document", "Technical details",
                           "The exact predefined action WinFix will run")
        table = KeyValueTable(label_width=160, style="caption")
        table.add("Action", proposal.tool, divider=False)
        table.add("Implementation", proposal.technical, divider=False)
        table.add("Parameters", ", ".join(f"{k}={v}" for k, v in proposal.parameters.items())
                  or "None", divider=False)
        table.add("Runs as", "Administrator (Windows will ask)" if proposal.requires_admin
                  and not is_admin() else "Current user", divider=False)
        table.add("Verification", "Repeats: " + ", ".join(
            check_catalog.info(t).label for t in proposal.verification_tools), divider=False)
        table.add("Safety", "Predefined action from WinFix's allow-list. No scripts or "
                  "commands from AI are ever run.", divider=False)
        details.content_layout.addWidget(table)
        self.add(details)

    def _confirm(self, proposal: RemediationProposal) -> None:
        dialog = ContentDialog(self.window(), "Apply this fix?",
                               "WinFix AI will make this change to your PC.",
                               primary="Apply fix", secondary="Cancel",
                               primary_icon="shield" if proposal.requires_admin else None)
        frame = QFrame()
        frame.setObjectName("ListCard")
        box = QVBoxLayout(frame)
        box.setContentsMargins(12, 0, 12, 0)
        table = KeyValueTable(label_width=150)
        table.add("Change", proposal.change, divider=False)
        table.add("Risk", _RISK_WORD[proposal.risk_level.value])
        table.add("Permission", "Administrator" if proposal.requires_admin else "Current user")
        table.add("Your files and apps", proposal.files_affected)
        box.addWidget(table)
        dialog.body.addWidget(frame)
        dialog.body.addWidget(Text("After the change, WinFix checks whether the problem is "
                                   "resolved and shows you the result.", "caption",
                                   "secondary", wrap=True))
        if proposal.risk_level.value == "high":
            confirm = QCheckBox("I understand the consequences of this change.")
            confirm.setFont(font("body"))
            dialog.body.addWidget(confirm)
            dialog.primary.setEnabled(False)
            confirm.toggled.connect(dialog.primary.setEnabled)

        def closed(accepted: bool) -> None:
            if accepted:
                self.ctx.controller.apply(proposal)

        dialog.open_async(closed)
        self._dialog = dialog

    # --- applying / verifying ---------------------------------------------------
    def _applying(self) -> None:
        session = self.session
        proposal = self.ctx.controller.pending_proposal or session.proposals[0]
        info = fix_info(proposal.tool)
        doing = running_title(proposal.title)
        self.add(header("Applying fix", f"{doing}. This usually takes "
                        f"{proposal.estimated_time[:1].lower()}{proposal.estimated_time[1:]}.",
                        caption=self._crumb()))
        self.add(24)
        card = Card(padding=(28, 24, 28, 12))
        self.timeline = Timeline()
        labels = [short_label(c) for c in session.diagnosis.possible_causes
                  if c.level in (Level.CAUTION, Level.CRITICAL)][:2]
        self.timeline.add_step("Diagnosis complete", " · ".join(labels) or
                               session.diagnosis.headline, "completed")
        approved = next((e for e in reversed(session.timeline) if e.kind == "approved"), None)
        self.timeline.add_step("Fix approved", f"Approved by you at "
                               f"{clock(approved.at) if approved else ''}".strip(), "completed")
        first = info.steps[0] if info.steps else doing
        detail = first
        if proposal.requires_admin and not is_admin():
            detail = "Windows may ask for administrator permission."
        self.timeline.add_step(doing, detail, "running")
        self.timeline.add_step("Verifying result", "Repeats the measurements WinFix took "
                               "before the fix", "queued")
        card.add(self.timeline)
        self.add(card)
        self.add(16)
        note = ("You can keep using your PC. WinFix won't restart your PC or close your apps."
                if proposal.tool != "reset_winsock" else
                "A restart is needed afterwards. WinFix won't restart your PC for you.")
        self.add(Footnote(note))

    def _verifying(self) -> None:
        self.add(header("Verifying the fix",
                        "WinFix is checking whether the problem has been resolved.",
                        caption=self._crumb()))
        self.add(20)
        bar = ProgressBar()
        bar.set_value(None)
        bar.setMaximumWidth(220)
        self.add(bar)
        self.add(20)
        table = CompareTable()
        for row in getattr(self, "pending", []):
            table.add_row(row.label, row.before, "", row.before_level.value, "info",
                          measuring=True)
        self.add(table)
        self.add(12)
        self.add(Footnote("WinFix repeats the same measurements it took before the fix, "
                          "so the comparison is like for like.", icon="info"))

    # --- result ----------------------------------------------------------------
    def _result(self) -> None:
        session = self.session
        v = session.verification
        self.add(header("Verification complete", caption=self._crumb()))
        self.add(20)
        state = "success" if v.improved else ("critical" if v.action_effective is False
                                              and not session.remediations[-1].success
                                              else "caution")
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addWidget(StatusIcon(state, 32), 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(vbox(Text(v.headline, "subtitle", wrap=True),
                            Text(v.summary, "body", "secondary", wrap=True), spacing=4), 1)
        self.add(head)
        self.add(24)
        if v.checks:
            self.add(Text("Before and after", "body_strong"))
            self.add(8)
            table = CompareTable()
            for c in v.checks:
                after_level = c.after_level.value
                if c.status in (CheckStatus.IMPROVED, CheckStatus.OK):
                    after_level = "ok"
                table.add_row(c.label, c.before, c.after, c.before_level.value, after_level)
            self.add(table)
            self.add(12)

        if v.improved:
            if v.note:
                self.add(Footnote(v.note), 16)
            done = Button("Done", "Accent")
            done.clicked.connect(self._done)
            details = Button("View technical details", "Standard")
            details.clicked.connect(lambda: self.ctx.navigate(
                "history_detail", session_id=session.id))
            self.add(hbox(done, details, stretch_at=1))
            return

        applied = session.remediations[-1].success
        if applied and v.found:
            card = Card(padding=(20, 18, 20, 18))
            card.add(Text("What WinFix found", "body_strong"))
            card.add(Text(v.found, "body", wrap=True))
            if v.note:
                card.add(Footnote(v.note))
            self.add(card)
            self.add(20)
        attempts_left = len(session.remediations) < self.ctx.controller.max_attempts()
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        if not applied:
            retry = Button("Try again", "Accent")
            retry.clicked.connect(lambda: self._confirm(self.ctx.controller.pending_proposal
                                                        or session.proposals[0]))
            retry.setEnabled(attempts_left)
            buttons.addWidget(retry)
        else:
            more = Button("Continue investigation", "Accent")
            more.setEnabled(attempts_left)
            more.clicked.connect(self._continue)
            buttons.addWidget(more)
        view = Button("View diagnostics", "Standard")
        view.clicked.connect(lambda: self.ctx.navigate("diagnostics"))
        stop = Button("Stop troubleshooting", "Subtle")
        stop.clicked.connect(self._stop)
        buttons.addWidget(view)
        buttons.addWidget(stop)
        buttons.addStretch(1)
        self.add(buttons)
        if not attempts_left:
            self.add(8)
            self.add(Text(f"WinFix has tried the maximum of "
                          f"{self.ctx.controller.max_attempts()} fixes for this session.",
                          "caption", "secondary"))

    def _continue(self) -> None:
        self.ctx.controller.continue_investigation()
        self.show_view("investigating")

    def _stop(self) -> None:
        self.ctx.controller.stop()
        self.ctx.navigate("home")

    def result_value(self) -> str:
        s = self.session
        return s.result.value if s else SessionResult.IN_PROGRESS.value
