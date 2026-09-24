"""Home: describe the problem, try an example, see recent sessions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from app.gui.icons import IconLabel
from app.gui.pages.base import AppContext, Page, relative_date, result_state
from app.gui.widgets.composite import EmptyState, Footnote
from app.gui.widgets.core import Button, Card, Divider, RowButton, SearchBox, Text
from app.gui.widgets.status import Status
from app.gui.workers import run_async
from app.knowledge.categories import category_icon

EXAMPLES = [
    ("speed", "My laptop is very slow"),
    ("wifi", "Wi-Fi keeps disconnecting"),
    ("update", "Windows Update isn't working"),
    ("disk", "My storage is almost full"),
]


class ProblemInput(Card):
    """'Describe the problem' card shared by Home and Troubleshoot."""

    def __init__(self, on_submit, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=(24, 22, 24, 24), spacing=0)
        self._on_submit = on_submit
        self.add(Text("Describe the problem", "body_strong"))
        self.body.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = SearchBox("Describe what's wrong with your PC...", height=46)
        self.input.setAccessibleName("Describe the problem")
        self.input.returnPressed.connect(self.submit)
        self.input.textChanged.connect(lambda _t: self._set_error(False))
        self.diagnose = Button("Diagnose", "Accent", height=46)
        self.diagnose.setMinimumWidth(124)
        self.diagnose.clicked.connect(self.submit)
        row.addWidget(self.input, 1)
        row.addWidget(self.diagnose)
        self.add(row)
        self.body.addSpacing(8)
        self.hint = Footnote("Use your own words. WinFix runs read-only checks first and "
                             "asks before changing anything.")
        self.error = Status("critical", "Describe the problem to start diagnosing.",
                            "caption", 12)
        self.error.label.set_role("critical")
        self.error.hide()
        self.add(self.hint)
        self.add(self.error)
        self.body.addSpacing(18)
        self.add(Divider())
        self.body.addSpacing(16)
        self.add(Text("Try an example", "caption", "secondary"))
        self.body.addSpacing(8)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        for icon, text in EXAMPLES:
            chip = Button(text, "Chip", icon)
            chip.clicked.connect(lambda _=False, t=text: self._use(t))
            chips.addWidget(chip)
        chips.addStretch(1)
        self.add(chips)

    def _use(self, text: str) -> None:
        self.input.setText(text)
        self.input.setFocus()

    def _set_error(self, error: bool) -> None:
        self.input.set_error(error)
        self.error.setVisible(error)
        self.hint.setVisible(not error)

    def submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            self._set_error(True)
            self.input.setFocus()
            return
        self._on_submit(text)


class SessionRow(RowButton):
    """A clickable recent/history session row."""

    def __init__(self, row: dict, on_open, parent: QWidget | None = None) -> None:
        super().__init__(parent, min_height=64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(16)
        layout.addWidget(IconLabel(category_icon(row.get("category")), "text", 20))
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(Text(_title(row["problem"]), "body"))
        texts.addWidget(Text(row.get("diagnosis") or "—", "caption", "secondary"))
        layout.addLayout(texts, 1)
        date = Text(relative_date(row.get("created_at")), "caption", "secondary")
        date.setFixedWidth(96)
        layout.addWidget(date)
        state, label = result_state(row.get("result"))
        status = Status(state, label)
        status.setFixedWidth(150)
        layout.addWidget(status)
        layout.addWidget(IconLabel("chevron_right", "text_secondary"))
        self.setAccessibleName(f"{row['problem']}, {label}")
        self.clicked.connect(lambda: on_open(row["id"]))


def _title(problem: str) -> str:
    text = problem.strip().rstrip(".")
    return text[:1].upper() + text[1:]


class HomePage(Page):
    key = nav_key = "home"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.add(Text("WinFix AI", "title"))
        self.add(4)
        self.add(Text("Troubleshoot Windows problems with evidence, not guesswork.",
                      "body", "secondary"))
        self.add(28)
        self.problem = ProblemInput(self._diagnose)
        self.add(self.problem)
        self.add(40)
        head = QHBoxLayout()
        head.addWidget(Text("Recent troubleshooting", "body_strong"))
        head.addStretch(1)
        view_all = Button("View all", "Hyperlink")
        view_all.clicked.connect(lambda: ctx.navigate("history"))
        head.addWidget(view_all)
        self.add(head)
        self.add(8)
        self.recent = QVBoxLayout()
        self.recent.setSpacing(4)
        self.add(self.recent)

    def _diagnose(self, problem: str) -> None:
        if self.ctx.controller.start(problem):
            self.problem.input.clear()
            self.ctx.navigate("troubleshoot")

    def on_show(self, **params) -> None:
        run_async(lambda: self.ctx.history.list_sessions(limit=3), self._show_recent,
                  lambda m, d: self._show_recent([]))

    def _show_recent(self, rows: list[dict]) -> None:
        while self.recent.count():
            item = self.recent.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not rows:
            action = Button("Troubleshoot a problem", "Accent")
            action.clicked.connect(lambda: self.problem.input.setFocus())
            self.recent.addWidget(EmptyState(
                "history", "No troubleshooting history yet",
                "Sessions you run appear here, with the evidence WinFix collected and any "
                "changes it made.", action))
            return
        for row in rows:
            self.recent.addWidget(SessionRow(row, lambda sid: self.ctx.navigate(
                "history_detail", session_id=sid)))
