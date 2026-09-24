"""Core Fluent-style controls: text, buttons, cards, inputs, toggles."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import (
    Property,
    QEvent,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui import icons, motion, theme


# --- typography ----------------------------------------------------------------
@lru_cache(maxsize=2)
def _family(display: bool) -> list[str]:
    available = set(QFontDatabase.families())
    wanted = theme.DISPLAY_FAMILIES if display else theme.TEXT_FAMILIES
    found = [f for f in wanted if f in available]
    return found or ["Segoe UI"]


def font(style: str = "body") -> QFont:
    spec = theme.TYPE[style]
    f = QFont()
    f.setFamilies(_family(spec.display))
    f.setPixelSize(spec.size)
    f.setWeight(QFont.Weight.DemiBold if spec.weight >= 600 else QFont.Weight.Normal)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


class Text(QLabel):
    """A label with a type ramp style and a color role (secondary, accent, ...)."""

    def __init__(self, text: str = "", style: str = "body", role: str | None = None,
                 wrap: bool = False, parent: QWidget | None = None,
                 selectable: bool = False) -> None:
        super().__init__(text, parent)
        self.setFont(font(style))
        self.setWordWrap(wrap)
        self.setTextFormat(Qt.TextFormat.PlainText)
        if role:
            self.setProperty("role", role)
        if selectable:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def set_role(self, role: str | None) -> None:
        self.setProperty("role", role or "")
        self.style().unpolish(self)
        self.style().polish(self)


# --- layout helpers --------------------------------------------------------------
def hbox(*items, spacing: int = 8, margins=(0, 0, 0, 0), stretch_at: int | None = None,
         align=None) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    _fill(layout, items, stretch_at, align)
    return layout


def vbox(*items, spacing: int = 8, margins=(0, 0, 0, 0), stretch_at: int | None = None,
         align=None) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    _fill(layout, items, stretch_at, align)
    return layout


def _fill(layout, items, stretch_at, align) -> None:
    for i, item in enumerate(items):
        if item is None:
            continue
        if isinstance(item, int):
            layout.addSpacing(item)
        elif isinstance(item, QLayout):
            layout.addLayout(item)
        elif align is not None:
            layout.addWidget(item, 0, align)
        else:
            layout.addWidget(item)
        if stretch_at is not None and i == stretch_at:
            layout.addStretch(1)
    if stretch_at == -1:
        layout.addStretch(1)


def host(layout: QLayout, parent: QWidget | None = None) -> QWidget:
    widget = QWidget(parent)
    widget.setLayout(layout)
    return widget


class Card(QFrame):
    """A card surface: 1 px stroke, 8 px radius."""

    def __init__(self, parent: QWidget | None = None, *, padding=(16, 16, 16, 16),
                 spacing: int = 8, name: str = "Card") -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*padding)
        self.body.setSpacing(spacing)

    def add(self, item) -> None:
        if isinstance(item, QLayout):
            self.body.addLayout(item)
        else:
            self.body.addWidget(item)


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None, vertical: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        if vertical:
            self.setFixedWidth(1)
        else:
            self.setFixedHeight(1)


# --- buttons -------------------------------------------------------------------
class Button(QPushButton):
    """Accent, Standard, Subtle or Hyperlink button with an optional themed icon."""

    def __init__(self, text: str = "", kind: str = "Standard", icon: str | None = None,
                 parent: QWidget | None = None, height: int = 32) -> None:
        super().__init__(text, parent)
        self.setObjectName(kind)
        self._icon_name = icon
        self.setFont(font("body"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(height)
        if text:
            self.setAccessibleName(text)
        self._refresh()
        theme.manager().changed.connect(self._refresh)

    def _refresh(self, _palette=None) -> None:
        if not self._icon_name:
            return
        token = {"Accent": "on_accent", "Hyperlink": "accent_text"}.get(self.objectName(),
                                                                         "text")
        self.setIcon(icons.icon(self._icon_name, token))
        self.setIconSize(QSize(16, 16))

    def set_icon_name(self, name: str | None) -> None:
        self._icon_name = name
        if name is None:
            self.setIcon(icons.QIcon())
        self._refresh()


class RowButton(QPushButton):
    """A clickable row whose content is a child layout (list and settings rows).

    QPushButton sizes itself from its own text and the stylesheet's
    ``min-height``; rows size from their layout instead and keep their own
    minimum height across theme changes.
    """

    def __init__(self, parent: QWidget | None = None, min_height: int = 48) -> None:
        super().__init__(parent)
        self.setObjectName("RowButton")
        self._min_height = min_height
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(min_height)

    def sizeHint(self) -> QSize:
        layout = self.layout()
        if layout is None:
            return super().sizeHint()
        hint = layout.sizeHint()
        return QSize(hint.width(), max(self._min_height, hint.height()))

    def event(self, event) -> bool:
        result = super().event(event)
        if event.type() in (QEvent.Type.Polish, QEvent.Type.StyleChange):
            if self.minimumHeight() != self._min_height:
                self.setMinimumHeight(self._min_height)
        return result


def accent(text: str, icon: str | None = None, **kw) -> Button:
    return Button(text, "Accent", icon, **kw)


def standard(text: str, icon: str | None = None, **kw) -> Button:
    return Button(text, "Standard", icon, **kw)


def subtle(text: str, icon: str | None = None, **kw) -> Button:
    return Button(text, "Subtle", icon, **kw)


def hyperlink(text: str, **kw) -> Button:
    return Button(text, "Hyperlink", None, **kw)


# --- combo box -----------------------------------------------------------------
class ComboBox(QComboBox):
    def __init__(self, items: list[tuple[str, object]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(font("body"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(32)
        for label, value in items:
            self.addItem(label, value)

    def value(self):
        return self.currentData()

    def set_value(self, value) -> None:
        index = self.findData(value)
        if index >= 0:
            self.setCurrentIndex(index)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        color = QColor(theme.palette().text_secondary).name()
        pm = icons.pixmap("chevron_down", color, 12, self.devicePixelRatioF())
        painter.drawPixmap(self.width() - 26, (self.height() - 12) // 2, pm)
        painter.end()


# --- text inputs -----------------------------------------------------------------
class SearchBox(QLineEdit):
    """Text box with a leading search glyph; focus adds a 2 px accent underline."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None,
                 height: int = 32, glyph: str | None = "search") -> None:
        super().__init__(parent)
        self._glyph = glyph
        self.setPlaceholderText(placeholder)
        self.setAccessibleName(placeholder or "Search")
        self.setFont(font("body"))
        self.setMinimumHeight(height)
        if glyph:
            self.setTextMargins(24, 0, 0, 0)

    def set_error(self, error: bool) -> None:
        self.setProperty("error", "true" if error else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._glyph:
            return
        painter = QPainter(self)
        color = QColor(theme.palette().text_secondary).name()
        pm = icons.pixmap(self._glyph, color, 16, self.devicePixelRatioF())
        painter.drawPixmap(12, (self.height() - 16) // 2, pm)
        painter.end()


# --- toggle switch ------------------------------------------------------------------
class ToggleSwitch(QAbstractButton):
    """Windows-style toggle with an 'On'/'Off' label to its left."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None,
                 show_label: bool = True) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._show_label = show_label
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(motion.NORMAL_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        self.setFont(font("body"))
        self.setFixedHeight(28)
        self.setFixedWidth(84 if show_label else 44)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self.setAccessibleDescription("On" if checked else "Off")
        if not motion.animations_enabled():
            self._set_knob(1.0 if checked else 0.0)
            return
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:
        return QSize(self.width(), 28)

    def paintEvent(self, _event) -> None:
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(self.width() - 42, 4, 40, 20)
        if self._show_label:
            painter.setPen(QColor(p.text if self.isEnabled() else p.text_disabled))
            painter.setFont(self.font())
            painter.drawText(QRectF(0, 0, track.left() - 10, 28),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             "On" if self.isChecked() else "Off")
        on = self.isChecked()
        enabled = self.isEnabled()
        if on:
            fill = QColor(p.accent if enabled else p.accent_disabled)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
        else:
            painter.setPen(QPen(QColor(p.strong_stroke if enabled else p.text_disabled), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        size = 12 if not self.underMouse() else 14
        x = track.left() + 4 + self._pos * (track.width() - 8 - 12) + (12 - size) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.on_accent if on else
                                (p.text_secondary if enabled else p.text_disabled)))
        painter.drawEllipse(QRectF(x, track.center().y() - size / 2, size, size))
        if self.hasFocus():
            painter.setPen(QPen(QColor(p.focus), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track.adjusted(-3, -3, 3, 3), 12, 12)
        painter.end()


class RadioButton(QAbstractButton):
    """Fluent radio: 20 px ring; selected shows a thick accent ring."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(24, 24)

    def sizeHint(self) -> QSize:
        return QSize(24, 24)

    def paintEvent(self, _event) -> None:
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(2, 2, 20, 20)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p.accent if self.isEnabled() else p.accent_disabled))
            painter.drawEllipse(ring)
            inner = 10 if self.underMouse() else 8
            painter.setBrush(QColor(p.on_accent))
            painter.drawEllipse(QRectF(12 - inner / 2, 12 - inner / 2, inner, inner))
        else:
            painter.setPen(QPen(QColor(p.strong_stroke if self.isEnabled()
                                       else p.text_disabled), 1))
            painter.setBrush(QColor(p.control_hover if self.underMouse() else p.control))
            painter.drawEllipse(ring.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.hasFocus():
            painter.setPen(QPen(QColor(p.focus), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring.adjusted(-1, -1, 1, 1))
        painter.end()


def text_field(placeholder: str = "", *, password: bool = False, width: int | None = None,
               accessible_name: str | None = None) -> SearchBox:
    """A plain text box (no search glyph), optionally masked."""
    field = SearchBox(placeholder, glyph=None)
    field.setAccessibleName(accessible_name or placeholder)
    if password:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    if width:
        field.setFixedWidth(width)
    return field


def expanding(widget: QWidget) -> QWidget:
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return widget

