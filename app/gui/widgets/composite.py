"""Composite WinFix components from the design specification."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui import theme
from app.gui.icons import IconLabel
from app.gui.widgets.core import Card, Divider, RowButton, Text, font, hbox, vbox
from app.gui.widgets.status import ProgressBar, Status, StatusIcon

_LEVEL_STATE = {"ok": "success", "info": "info", "caution": "caution",
                "critical": "critical"}


class FitText(Text):
    """Single-line text that shrinks (down to ``min_pixel_size``) and then elides
    to fit its width, so long values like app names never get clipped."""

    def __init__(self, text: str, style: str = "body", role: str | None = None,
                 min_pixel_size: int | None = None, parent: QWidget | None = None) -> None:
        super().__init__("", style, role, parent=parent)
        self._full = text
        self._base = self.font().pixelSize()
        self._min = min_pixel_size or self._base
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt override
        self._full = text
        self._refit()

    def text_full(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refit()

    def _refit(self) -> None:
        width = max(1, self.contentsRect().width())
        f = self.font()
        size = self._base
        f.setPixelSize(size)
        while size > self._min and QFontMetrics(f).horizontalAdvance(self._full) > width:
            size -= 1
            f.setPixelSize(size)
        if f.pixelSize() != self.font().pixelSize():
            self.setFont(f)
        elided = QFontMetrics(f).elidedText(self._full, Qt.TextElideMode.ElideRight, width)
        super().setText(elided)


class EvidenceCard(Card):
    """Measured value, context and a plain-language status."""

    def __init__(self, label: str, icon: str, value: str, detail: str, level: str,
                 status_text: str, progress: float | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=(16, 16, 16, 14), spacing=6)
        self.setMinimumWidth(170)
        self.add(hbox(IconLabel(icon, "text_secondary"),
                      FitText(label, "caption", "secondary"), spacing=8))
        value_text = FitText(value, "value", min_pixel_size=18)
        value_text.setToolTip(value)
        self.add(value_text)
        if progress is not None:
            bar = ProgressBar(meter=True)
            bar.set_value(progress)
            self.add(bar)
        else:
            self.body.addSpacing(4)
        self.add(Text(detail, "caption", "secondary", wrap=True))
        self.add(Status(_LEVEL_STATE.get(level, "info"), status_text, "caption", 12))
        self.setAccessibleName(f"{label}: {value}. {detail}. {status_text}")


class FlowGrid(QWidget):
    """Lays equal-width cards in as many columns as fit (like the design's
    five-across evidence row that wraps to three when narrow)."""

    def __init__(self, min_width: int = 180, spacing: int = 8,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = min_width
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)
        # The grid's own minimum is "all columns"; this widget can shrink to
        # one column instead, so let minimumSizeHint decide.
        self._grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._items: list[QWidget] = []
        self._columns = 0

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        widest = max((w.minimumSizeHint().width() for w in self._items), default=0)
        return QSize(max(widest, 1), super().minimumSizeHint().height())

    def set_items(self, widgets: list[QWidget]) -> None:
        for w in self._items:
            self._grid.removeWidget(w)
            w.deleteLater()
        self._items = list(widgets)
        self._columns = 0
        self._relayout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        if not self._items:
            return
        width = max(1, self.width())
        columns = max(1, min(len(self._items), (width + 8) // (self._min + 8)))
        if columns == self._columns:
            return
        self._columns = columns
        for w in self._items:
            self._grid.removeWidget(w)
        for i, w in enumerate(self._items):
            self._grid.addWidget(w, i // columns, i % columns)
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 1 if c < columns else 0)


class ResponsiveColumns(QWidget):
    """Main column plus a side panel; the panel moves below when narrow."""

    def __init__(self, breakpoint: int = 760, main_stretch: int = 7, side_stretch: int = 3,
                 spacing: int = 24, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._breakpoint = breakpoint
        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(spacing)
        self._box.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.main = QVBoxLayout()
        self.main.setSpacing(0)
        self.side = QVBoxLayout()
        self.side.setSpacing(0)
        self._box.addLayout(self.main, main_stretch)
        self._box.addLayout(self.side, side_stretch)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(max(self.main.minimumSize().width(), self.side.minimumSize().width()),
                     super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        direction = (QBoxLayout.Direction.TopToBottom if self.width() < self._breakpoint
                     else QBoxLayout.Direction.LeftToRight)
        if self._box.direction() != direction:
            self._box.setDirection(direction)


class DiagnosticRow(QFrame):
    """A check on the progress screen: icon, name, description, status."""

    def __init__(self, icon: str, name: str, description: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        layout.addWidget(IconLabel(icon, "text_secondary"), 0, Qt.AlignmentFlag.AlignVCenter)
        self.name = Text(name, "body")
        self.description = Text(description, "caption", "secondary")
        layout.addLayout(vbox(self.name, self.description, spacing=2), 1)
        self.status = Status("queued")
        self.status.setFixedWidth(128)
        layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setAccessibleName(name)

    def set_state(self, state: str, description: str | None = None) -> None:
        self.status.set(state)
        if description is not None:
            self.description.setText(description)
        self.setAccessibleDescription(f"{self.status.label.text()}. "
                                      f"{self.description.text()}")


class ListCard(QFrame):
    """A card holding rows separated by dividers."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ListCard")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.rows: list[QWidget] = []

    def add_row(self, widget: QWidget) -> None:
        if self.rows:
            self._layout.addWidget(Divider())
        self._layout.addWidget(widget)
        self.rows.append(widget)

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows = []


class SettingsRow(RowButton):
    """Icon, title, description and a trailing control (or a chevron)."""

    def __init__(self, icon: str, title: str, description: str = "",
                 trailing: QWidget | None = None, *, chevron: bool = False,
                 value: str | None = None, parent: QWidget | None = None,
                 icon_widget: QWidget | None = None) -> None:
        super().__init__(parent, min_height=68)
        clickable = chevron
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable
                       else Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if clickable else Qt.FocusPolicy.NoFocus)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        layout.addWidget(icon_widget or IconLabel(icon, "text", 20), 0,
                         Qt.AlignmentFlag.AlignVCenter)
        self.title = Text(title, "body")
        self.description = Text(description, "caption", "secondary", wrap=True)
        layout.addLayout(vbox(self.title, self.description, spacing=2), 1)
        if not description:
            self.description.hide()
        if value is not None:
            self.value = Text(value, "body", "secondary")
            layout.addWidget(self.value, 0, Qt.AlignmentFlag.AlignVCenter)
        if trailing is not None:
            layout.addWidget(trailing, 0, Qt.AlignmentFlag.AlignVCenter)
        if chevron:
            layout.addWidget(IconLabel("chevron_right", "text_secondary"), 0,
                             Qt.AlignmentFlag.AlignVCenter)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)


    def set_description(self, text: str, role: str = "secondary") -> None:
        self.description.setText(text)
        self.description.set_role(role)
        self.description.setVisible(bool(text))
        self.setAccessibleDescription(text)


class Expander(QFrame):
    """Collapsible card: header row with chevron, content below."""

    toggled = Signal(bool)

    def __init__(self, icon: str, title: str, description: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ListCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = RowButton(min_height=64)
        self.header.setStyleSheet("QPushButton#RowButton { border: none; }")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setAccessibleName(title)
        row = QHBoxLayout(self.header)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(16)
        row.addWidget(IconLabel(icon, "text", 20), 0, Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(vbox(Text(title, "body"), Text(description, "caption", "secondary"),
                           spacing=2), 1)
        self._chevron = IconLabel("chevron_down", "text_secondary")
        row.addWidget(self._chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(self.header)
        self._divider = Divider()
        self._divider.hide()
        outer.addWidget(self._divider)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(52, 12, 16, 16)
        self.content_layout.setSpacing(8)
        self.content.hide()
        outer.addWidget(self.content)
        self.header.clicked.connect(self.toggle)

    def toggle(self) -> None:
        self.set_expanded(not self.content.isVisible())

    def set_expanded(self, expanded: bool) -> None:
        self.content.setVisible(expanded)
        self._divider.setVisible(expanded)
        self._chevron.set_icon("chevron_up" if expanded else "chevron_down")
        self.header.setAccessibleDescription("Expanded" if expanded else "Collapsed")
        self.toggled.emit(expanded)


class KeyValueTable(QWidget):
    """Label/value rows with dividers (Recommended fix and technical details)."""

    def __init__(self, label_width: int = 190, parent: QWidget | None = None,
                 style: str = "body") -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._label_width = label_width
        self._style = style
        self._count = 0

    def add(self, label: str, value, *, divider: bool = True) -> None:
        if self._count and divider:
            self._layout.addWidget(Divider())
        row = QHBoxLayout()
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(16)
        key = Text(label, self._style, "secondary")
        key.setFixedWidth(self._label_width)
        key.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        row.addWidget(key, 0, Qt.AlignmentFlag.AlignTop)
        if isinstance(value, str):
            value = Text(value, self._style, wrap=True, selectable=True)
        row.addWidget(value, 1)
        self._layout.addLayout(row)
        self._count += 1


class CompareTable(QFrame):
    """Check / Before / After table used by verification screens."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ListCard")
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(16, 0, 16, 0)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(0)
        self._grid.setColumnStretch(0, 4)
        self._grid.setColumnStretch(1, 3)
        self._grid.setColumnStretch(2, 3)
        self._row = 0
        for col, head in enumerate(("Check", "Before", "After")):
            self._cell(Text(head, "caption", "secondary"), col, header=True)
        self._row += 1

    def _cell(self, widget: QWidget, col: int, header: bool = False) -> None:
        wrapper = QWidget()
        lay = QVBoxLayout(wrapper)
        lay.setContentsMargins(0, 10 if header else 12, 0, 10 if header else 12)
        lay.addWidget(widget)
        self._grid.addWidget(wrapper, self._row * 2, col)

    def add_row(self, label: str, before: str, after: str, before_level: str = "info",
                after_level: str = "info", measuring: bool = False) -> None:
        divider = Divider()
        self._grid.addWidget(divider, self._row * 2 - 1, 0, 1, 3)
        self._cell(Text(label, "body"), 0)
        self._cell(self._value(before, before_level), 1)
        self._cell(Status("running", "Measuring…") if measuring
                   else self._value(after, after_level), 2)
        self._row += 1

    @staticmethod
    def _value(text: str, level: str) -> QWidget:
        if level in ("ok", "caution", "critical"):
            return Status(_LEVEL_STATE[level], text)
        return Text(text, "body")


class Timeline(QWidget):
    """Vertical progress steps: completed, running, waiting."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.steps: list[tuple[StatusIcon, Text, Text]] = []

    def add_step(self, title: str, detail: str = "", state: str = "queued") -> int:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        icon_col = QVBoxLayout()
        icon_col.setSpacing(0)
        icon_col.setContentsMargins(0, 2, 0, 0)
        icon = StatusIcon(state, 18)
        icon_col.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        icon_col.addWidget(_Connector(), 1, Qt.AlignmentFlag.AlignHCenter)
        lay.addLayout(icon_col)
        heading = Text(title, "body_strong" if state == "running" else "body",
                       None if state != "queued" else "secondary")
        sub = Text(detail, "caption", "secondary", wrap=True)
        lay.addLayout(vbox(heading, sub, 18, spacing=2), 1)
        self._layout.addWidget(row)
        self.steps.append((icon, heading, sub))
        self._refresh_connectors()
        return len(self.steps) - 1

    def set_step(self, index: int, state: str, title: str | None = None,
                 detail: str | None = None) -> None:
        icon, heading, sub = self.steps[index]
        icon.set_state(state)
        if title is not None:
            heading.setText(title)
        heading.setFont(font("body_strong" if state == "running" else "body"))
        heading.set_role("secondary" if state == "queued" else None)
        if detail is not None:
            sub.setText(detail)

    def _refresh_connectors(self) -> None:
        for i in range(self._layout.count()):
            row = self._layout.itemAt(i).widget()
            connector = row.findChild(_Connector) if row else None
            if connector:
                connector.setVisible(i < self._layout.count() - 1)


class _Connector(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(18)
        self.setMinimumHeight(24)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        color = QColor(theme.palette().strong_stroke)
        color.setAlphaF(0.6)
        painter.setPen(QPen(color, 1))
        x = self.width() / 2
        painter.drawLine(QPointF(x, 4), QPointF(x, self.height() - 4))
        painter.end()


class Breadcrumb(QWidget):
    """'Diagnosis  >  Recommended fix' — earlier parts are clickable."""

    navigate = Signal(int)

    def __init__(self, parts: list[str], style: str = "title",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._links: list[QPushButton] = []
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if last:  # shrinks, then elides, instead of widening the page
                current = FitText(part, style, min_pixel_size=20)
                current.setToolTip(part)
                current.setMinimumWidth(120)
                layout.addWidget(current, 1)
            else:
                button = QPushButton(part)
                button.setFlat(True)
                button.setFont(font(style))
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(lambda _=False, index=i: self.navigate.emit(index))
                self._links.append(button)
                layout.addWidget(button)
                layout.addWidget(IconLabel("chevron_right", "text_secondary", 16), 0,
                                 Qt.AlignmentFlag.AlignVCenter)
        self._restyle()
        theme.manager().changed.connect(self._restyle)

    def _restyle(self, _palette=None) -> None:
        p = theme.palette()
        for button in self._links:
            button.setStyleSheet(
                "QPushButton { border: none; background: transparent; padding: 0;"
                f" color: {p.text_secondary}; }}"
                f"QPushButton:hover {{ color: {p.text}; }}")


class EmptyState(QWidget):
    def __init__(self, icon: str, title: str, message: str, action: QWidget | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 32, 0, 32)
        layout.setSpacing(8)
        layout.addWidget(IconLabel(icon, "text_secondary", 32), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        title_label = Text(title, "subtitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title_label)
        body = Text(message, "body", "secondary", wrap=True)
        body.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        body.setMaximumWidth(420)
        # Stretches (not an alignment flag) center it, so the label gets real
        # width to wrap into instead of its minimum.
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(body, 4)
        row.addStretch(1)
        layout.addLayout(row)
        self.message = body
        if action is not None:
            layout.addSpacing(8)
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)


class Footnote(QWidget):
    """(i) caption text, used under cards."""

    def __init__(self, text: str, icon: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(IconLabel(icon, "text_secondary", 16), 0, Qt.AlignmentFlag.AlignTop)
        label = Text(text, "caption", "secondary", wrap=True)
        layout.addWidget(label, 1)


class NumberBadge(QWidget):
    """Numbered circle for the 'Possible causes' list."""

    def __init__(self, number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._n = number
        self.setFixedSize(24, 24)

    def paintEvent(self, _event) -> None:
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(p.strong_stroke), 1))
        painter.drawEllipse(QRectF(1.5, 1.5, 21, 21))
        painter.setPen(QColor(p.text))
        painter.setFont(font("caption"))
        painter.drawText(QRectF(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, str(self._n))
        painter.end()


def section_title(text: str) -> Text:
    return Text(text, "body_strong")

