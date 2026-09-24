"""Page scaffold and shared helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLayout, QScrollArea, QVBoxLayout, QWidget

from app.core.models import SessionResult
from app.gui.widgets.core import Text

if TYPE_CHECKING:
    from app.core.history import HistoryStore
    from app.gui.controller import TroubleshootController

CONTENT_MAX_WIDTH = 1040


@dataclass
class AppContext:
    window: Any
    history: "HistoryStore"
    controller: "TroubleshootController"
    demo: Any = None

    def navigate(self, key: str, **params) -> None:
        self.window.navigate(key, **params)

    def error(self, title: str, message: str, detail: str = "") -> None:
        self.window.show_error(title, message, detail)

    def notify(self, title: str, message: str) -> None:
        self.window.notify(title, message)


class Page(QWidget):
    """A scrollable page with a left-aligned content column."""

    key = ""
    nav_key = ""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        row = QHBoxLayout(inner)
        row.setContentsMargins(0, 0, 0, 0)
        self.column = QWidget()
        self.column.setMaximumWidth(CONTENT_MAX_WIDTH + 80)
        self.content = QVBoxLayout(self.column)
        self.content.setContentsMargins(40, 32, 40, 40)
        self.content.setSpacing(0)
        self.content.addStretch(1)  # keeps content top-aligned; add() inserts above it
        row.addWidget(self.column, 1)
        row.addStretch(0)
        self.scroll.setWidget(inner)
        outer.addWidget(self.scroll)

    def on_show(self, **params) -> None:
        """Called each time the page becomes visible."""

    def on_hide(self) -> None:
        """Called when navigating away."""

    def clear(self) -> None:
        _clear(self.content)
        self.content.addStretch(1)
        self.scroll.verticalScrollBar().setValue(0)

    def add(self, item, spacing_after: int = 0) -> None:
        index = self.content.count() - 1
        if isinstance(item, QLayout):
            self.content.insertLayout(index, item)
        elif isinstance(item, int):
            self.content.insertSpacing(index, item)
            return
        else:
            self.content.insertWidget(index, item)
        if spacing_after:
            self.content.insertSpacing(index + 1, spacing_after)


def _clear(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


def header(title: str, subtitle: str | None = None, *, caption: str | None = None,
           actions: list[QWidget] | None = None, style: str = "title") -> QWidget:
    """Page header: optional breadcrumb caption, title, subtitle, right actions."""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    col = QVBoxLayout()
    col.setSpacing(4)
    if caption:
        col.addWidget(Text(caption, "caption", "secondary"))
    col.addWidget(Text(title, style) if isinstance(title, str) else title)
    if subtitle:
        col.addWidget(Text(subtitle, "body", "secondary", wrap=True))
    layout.addLayout(col, 1)
    for action in actions or []:
        layout.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)
    return widget


def relative_date(value: str | datetime | None) -> str:
    if not value:
        return ""
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    today = datetime.now().astimezone().date()
    days = (today - local.date()).days
    if days == 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if local.year != today.year:
        return f"{local:%b} {local.day}, {local.year}"
    return f"{local:%b} {local.day}"


def clock(value: datetime | None) -> str:
    if not value:
        return ""
    local = value.astimezone()
    return local.strftime("%I:%M %p").lstrip("0")


RESULT_STATE = {
    SessionResult.RESOLVED.value: ("resolved", "Resolved"),
    SessionResult.NOT_RESOLVED.value: ("not_resolved", "Not resolved"),
    SessionResult.NO_ISSUE.value: ("no_issue", "No problem found"),
    SessionResult.STOPPED.value: ("stopped", "Stopped by you"),
    SessionResult.FAILED.value: ("failed", "Failed"),
    SessionResult.IN_PROGRESS.value: ("in_progress", "In progress"),
}


def result_state(result: str | None) -> tuple[str, str]:
    return RESULT_STATE.get(result or "in_progress", ("in_progress", "In progress"))


def column(*widgets, spacing: int = 8) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, QLayout):
            layout.addLayout(w)
        elif isinstance(w, int):
            layout.addSpacing(w)
        elif w is not None:
            layout.addWidget(w)
    return layout
