"""History list and History detail."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from app.core.models import Level, Session
from app.core.report import session_report
from app.gui.icons import IconLabel
from app.gui.pages.base import AppContext, Page, clock, header, result_state
from app.gui.widgets.composite import (
    Breadcrumb,
    CompareTable,
    EmptyState,
    KeyValueTable,
    ListCard,
)
from app.gui.widgets.core import Button, Card, ComboBox, RowButton, SearchBox, Text, vbox
from app.gui.widgets.dialog import ContentDialog
from app.gui.widgets.status import Status, StatusIcon
from app.gui.workers import run_async
from app.knowledge.checks import info as check_info

_FILTERS = [("All results", None), ("Resolved", "resolved"), ("Not resolved", "not_resolved"),
            ("Stopped by you", "stopped"), ("No problem found", "no_issue")]


class HistoryRow(RowButton):
    def __init__(self, row: dict, on_open, parent: QWidget | None = None) -> None:
        super().__init__(parent, min_height=56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)
        date = Text(_short(row), "body", "secondary")
        date.setFixedWidth(92)
        layout.addWidget(date)
        problem = Text(_title(row["problem"]), "body", wrap=True)
        layout.addWidget(problem, 3)
        layout.addWidget(Text(row.get("diagnosis") or "—", "body", "secondary", wrap=True), 3)
        state, label = result_state(row.get("result"))
        status = Status(state, label)
        status.setFixedWidth(160)
        layout.addWidget(status)
        layout.addWidget(IconLabel("chevron_right", "text_secondary"))
        self.setAccessibleName(f"{row['problem']}. {row.get('diagnosis') or ''}. {label}")
        self.clicked.connect(lambda: on_open(row["id"]))


def _short(row: dict) -> str:
    dt = datetime.fromisoformat(row["created_at"]).astimezone()
    if dt.year != datetime.now().year:
        return f"{dt:%b} {dt.day}, {dt.year}"
    return f"{dt:%b} {dt.day}"


def _title(problem: str) -> str:
    text = problem.strip().rstrip(".")
    return text[:1].upper() + text[1:]


class HistoryPage(Page):
    key = nav_key = "history"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        clear = Button("Clear history", "Subtle", "delete")
        clear.clicked.connect(self._clear_history)
        self.add(header("History", "Troubleshooting sessions on this PC. History is stored "
                        "locally.", actions=[clear]))
        self.add(24)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search = SearchBox("Search history")
        self.search.setMaximumWidth(330)
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        self.filter = ComboBox(_FILTERS)
        self.filter.setMinimumWidth(165)
        self.filter.currentIndexChanged.connect(lambda _i: self.reload())
        self.count = Text("", "caption", "secondary")
        controls.addWidget(self.search, 1)
        controls.addWidget(self.filter)
        controls.addStretch(1)
        controls.addWidget(self.count)
        self.add(controls)
        self.add(20)
        heads = QHBoxLayout()
        heads.setContentsMargins(16, 0, 16, 0)
        heads.setSpacing(16)
        for text, width, stretch in (("Date", 92, 0), ("Problem", 0, 3), ("Diagnosis", 0, 3),
                                     ("Result", 160, 0)):
            label = Text(text, "caption", "secondary")
            if width:
                label.setFixedWidth(width)
            heads.addWidget(label, stretch)
        heads.addSpacing(16)
        self.add(heads)
        self.add(8)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        self.add(self.rows)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self.reload)

    def on_show(self, **params) -> None:
        self.reload()

    def reload(self) -> None:
        search, result = self.search.text().strip(), self.filter.value()
        run_async(lambda: self.ctx.history.list_sessions(search=search, result=result),
                  self._render, lambda m, d: self.ctx.error("Couldn't load history", m, d))

    def _render(self, rows: list[dict]) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.count.setText(f"{len(rows)} session{'s' if len(rows) != 1 else ''}")
        if not rows:
            filtered = bool(self.search.text().strip() or self.filter.value())
            action = None
            if not filtered:
                action = Button("Troubleshoot a problem", "Accent")
                action.clicked.connect(lambda: self.ctx.navigate("troubleshoot"))
            self.rows.addWidget(EmptyState(
                "history", "No matching sessions" if filtered else
                "No troubleshooting history yet",
                "Try a different search or filter." if filtered else
                "Sessions you run appear here, with the evidence WinFix collected and any "
                "changes it made.", action))
            return
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        group = None
        for row in rows:
            created = datetime.fromisoformat(row["created_at"])
            name = "This week" if created >= week_ago else "Earlier"
            if name != group:
                if group is not None:
                    self.rows.addSpacing(16)
                label = Text(name, "body_strong")
                label.setContentsMargins(0, 0, 0, 4)
                self.rows.addWidget(label)
                group = name
            self.rows.addWidget(HistoryRow(row, lambda sid: self.ctx.navigate(
                "history_detail", session_id=sid)))

    def _clear_history(self) -> None:
        dialog = ContentDialog(self.window(), "Clear history?",
                               "All troubleshooting sessions stored on this PC will be "
                               "deleted. Changes WinFix made to your PC are not undone.",
                               primary="Clear history", secondary="Cancel")

        def closed(accepted: bool) -> None:
            if accepted:
                run_async(self.ctx.history.delete_all, lambda _n: self.reload())

        dialog.open_async(closed)


class HistoryDetailPage(Page):
    key = "history_detail"
    nav_key = "history"

    def on_show(self, session_id: str | None = None, **params) -> None:
        if session_id:
            self._session_id = session_id
        run_async(lambda: self.ctx.history.load_session(self._session_id), self._render,
                  lambda m, d: self.ctx.error("Couldn't open this session", m, d))

    def _render(self, session: Session | None) -> None:
        self.clear()
        if session is None:
            self.add(EmptyState("history", "Session not found",
                                "It may have been removed when history was cleared."))
            return
        self.session = session
        export = Button("Export report", "Standard", "export")
        export.clicked.connect(self._export)
        again = Button("Troubleshoot again", "Standard", "refresh")
        again.clicked.connect(self._again)
        crumb = Breadcrumb(["History", _title(session.problem)])
        crumb.navigate.connect(lambda _i: self.ctx.navigate("history"))
        self.add(header(crumb, actions=[export, again]))
        self.add(8)
        state, label = result_state(session.result.value)
        meta = QHBoxLayout()
        meta.setSpacing(10)
        status = Status(state, label, "body_strong")
        meta.addWidget(status)
        started = session.created_at.astimezone()
        bits = [started.strftime("%b %d, %Y, %I:%M %p").replace(" 0", " ")]
        if session.finished_at:
            minutes = max(1, round((session.finished_at - session.created_at).total_seconds()
                                   / 60))
            bits.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        bits.append("Analyzed with cloud AI" if session.cloud.sent else "Analyzed on this PC")
        meta.addWidget(Text("  ·  ".join(bits), "body", "secondary"))
        meta.addStretch(1)
        self.add(meta)
        self.add(24)

        columns = QHBoxLayout()
        columns.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(0)
        right = QVBoxLayout()
        right.setSpacing(0)
        columns.addLayout(left, 7)
        columns.addLayout(right, 3)
        self.add(columns)

        def section(layout, title, widget, gap=24):
            layout.addWidget(Text(title, "body_strong"))
            layout.addSpacing(8)
            layout.addWidget(widget)
            layout.addSpacing(gap)

        quote = Card(padding=(16, 14, 16, 14))
        quote.add(Text(f"“{session.problem}”", "body", wrap=True))
        section(left, "You described", quote)

        d = session.diagnosis
        if d:
            card = Card(padding=(16, 14, 16, 14))
            row = QHBoxLayout()
            row.setSpacing(12)
            row.addWidget(StatusIcon({Level.OK: "success", Level.INFO: "info",
                                      Level.CAUTION: "caution", Level.CRITICAL: "critical"}
                                     [d.level]), 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(vbox(Text(session.short_diagnosis(), "body_strong"),
                               Text(d.summary, "body", "secondary", wrap=True), spacing=2), 1)
            checks = Button(f"View all {len(session.checks)} checks", "Hyperlink")
            row.addWidget(checks, 0, Qt.AlignmentFlag.AlignTop)
            card.add(row)
            self.checks_list = self._checks(session)
            self.checks_list.hide()
            card.add(self.checks_list)
            checks.clicked.connect(lambda: self.checks_list.setVisible(
                not self.checks_list.isVisible()))
            section(left, "Diagnosis", card)

        if session.remediations:
            for outcome in session.remediations:
                proposal = next((p for p in session.proposals if p.tool == outcome.tool), None)
                card = Card(padding=(16, 14, 16, 14))
                row = QHBoxLayout()
                row.setSpacing(12)
                row.addWidget(IconLabel("troubleshoot", "accent", 16), 0,
                              Qt.AlignmentFlag.AlignTop)
                details = [f"{(proposal.risk_level.value if proposal else 'low').title()} risk",
                           f"Approved by you at {clock(outcome.approved_at)}"]
                if outcome.elevated:
                    details.append("Administrator permission granted")
                if not outcome.success:
                    details.append("Not applied: " + str((outcome.error or {})
                                                         .get("message", ""))[:120])
                row.addLayout(vbox(Text(proposal.title if proposal else outcome.tool,
                                        "body_strong"),
                                   Text(" · ".join(details), "body", "secondary", wrap=True),
                                   spacing=2), 1)
                card.add(row)
                section(left, "Fix applied", card, 12)
            left.addSpacing(12)
        elif session.approval_status == "declined":
            card = Card(padding=(16, 14, 16, 14))
            card.add(Text("No changes were made. You chose not to apply the fix.", "body"))
            section(left, "Fix", card)

        for i, v in enumerate(session.verifications, 1):
            table = CompareTable()
            for c in v.checks:
                table.add_row(c.label, c.before, c.after, c.before_level.value,
                              "ok" if c.status.value in ("ok", "improved")
                              else c.after_level.value)
            title = "Verification" if len(session.verifications) == 1 else f"Verification {i}"
            section(left, title, table)
        left.addStretch(1)

        timeline = Card(padding=(16, 14, 16, 14), spacing=10)
        for event in session.timeline:
            row = QHBoxLayout()
            row.setSpacing(12)
            dot = StatusIcon("success" if event.kind == "verified" and
                             "resolved" in event.title and "not" not in event.title
                             else "queued", 10)
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(vbox(Text(event.title, "body", wrap=True),
                               Text(clock(event.at), "caption", "secondary"), spacing=0), 1)
            timeline.add(row)
        section(right, "Timeline", timeline)

        details = Card(padding=(16, 6, 16, 6))
        table = KeyValueTable(label_width=110)
        table.add("Session ID", session.display_id, divider=False)
        table.add("Checks run", str(sum(1 for c in session.checks if c.status == "completed")),
                  divider=False)
        table.add("Changes made", str(session.changes_made), divider=False)
        table.add("Sent to cloud", ", ".join(session.cloud.items) if session.cloud.sent
                  else "Nothing", divider=False)
        details.add(table)
        section(right, "Details", details)
        right.addStretch(1)

    def _checks(self, session: Session) -> QWidget:
        box = ListCard()
        for check in session.checks:
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(12)
            lay.addWidget(IconLabel(check_info(check.tool).icon, "text_secondary"))
            lay.addLayout(vbox(Text(check.label, "body"),
                               Text(f"{check.summary} · {check.source}", "caption",
                                    "secondary", wrap=True), spacing=0), 1)
            lay.addWidget(Status(check.status))
            box.add_row(row)
        return box

    def _export(self) -> None:
        session = self.session
        default = f"{session.display_id}.txt"
        path, selected = QFileDialog.getSaveFileName(
            self, "Export report", default, "Text report (*.txt);;JSON (*.json)")
        if not path:
            return
        try:
            if path.lower().endswith(".json") or "JSON" in selected:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(session.model_dump_json(indent=2))
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(session_report(session))
        except OSError as exc:
            self.ctx.error("Couldn't export the report", str(exc))
            return
        self.ctx.notify("Report exported", path)

    def _again(self) -> None:
        if self.ctx.controller.start(self.session.problem):
            self.ctx.navigate("troubleshoot")

