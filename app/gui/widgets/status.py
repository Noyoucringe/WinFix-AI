"""Status indicators, progress ring/bar, and InfoBar.

Every status pairs a distinct icon *shape* with a text label, so meaning never
depends on color alone: check (success), exclamation (caution), cross
(critical/failed), "i" (information), spinning ring (running), empty circle
(queued / stopped).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from app.gui import motion, theme
from app.gui.widgets.core import Button, Text

STATUS_TEXT = {
    "completed": "Completed", "running": "Running", "queued": "Queued",
    "failed": "Failed", "cancelled": "Cancelled", "resolved": "Resolved",
    "not_resolved": "Not resolved", "no_issue": "No problem found",
    "stopped": "Stopped by you", "in_progress": "In progress",
}

# State -> (shape, color token)
_SHAPES = {
    "success": ("check", "success"), "completed": ("check", "success"),
    "resolved": ("check", "success"), "ok": ("check", "success"),
    "no_issue": ("check", "success"),
    "caution": ("bang", "caution"), "not_resolved": ("bang", "caution"),
    "critical": ("cross", "critical"), "failed": ("cross", "critical"),
    "info": ("info", "accent"),
    "running": ("ring", "accent"), "in_progress": ("ring", "accent"),
    "queued": ("empty", "text_secondary"), "stopped": ("empty", "text_secondary"),
    "cancelled": ("empty", "text_secondary"),
}


class StatusIcon(QWidget):
    def __init__(self, state: str = "queued", size: int = 16,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._spin)
        self.setFixedSize(size, size)
        self.set_state(state)

    def set_state(self, state: str) -> None:
        self._state = state
        shape, _ = _SHAPES.get(state, ("empty", "text_secondary"))
        # Progress indicators keep moving even with reduced motion (per spec).
        if shape == "ring":
            self._timer.start()
        else:
            self._timer.stop()
        self.setAccessibleName(STATUS_TEXT.get(state, state))
        self.update()

    def _spin(self) -> None:
        self._angle = (self._angle + 360 * 16 / motion.PROGRESS_LOOP_MS) % 360
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

    def paintEvent(self, _event) -> None:
        p = theme.palette()
        shape, token = _SHAPES.get(self._state, ("empty", "text_secondary"))
        color = QColor(getattr(p, token))
        s = float(self._size)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, s - 2, s - 2)
        if shape == "empty":
            painter.setPen(QPen(color, 1.2))
            painter.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        elif shape == "ring":
            pen = QPen(color, max(1.5, s / 9))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect.adjusted(1, 1, -1, -1), int(-self._angle * 16), 100 * 16)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(rect)
            glyph = QColor(p.on_status if token != "accent" else p.on_accent)
            pen = QPen(glyph, max(1.4, s / 10))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            c = rect.center()
            k = s / 16
            if shape == "check":
                path = QPainterPath(QPointF(c.x() - 3.2 * k, c.y() + 0.2 * k))
                path.lineTo(c.x() - 1.0 * k, c.y() + 2.4 * k)
                path.lineTo(c.x() + 3.4 * k, c.y() - 2.2 * k)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
            elif shape == "cross":
                d = 2.6 * k
                painter.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
                painter.drawLine(QPointF(c.x() + d, c.y() - d), QPointF(c.x() - d, c.y() + d))
            elif shape == "bang":
                painter.drawLine(QPointF(c.x(), c.y() - 3.4 * k), QPointF(c.x(), c.y() + 0.6 * k))
                painter.drawPoint(QPointF(c.x(), c.y() + 3.2 * k))
            elif shape == "info":
                painter.drawLine(QPointF(c.x(), c.y() - 0.6 * k), QPointF(c.x(), c.y() + 3.4 * k))
                painter.drawPoint(QPointF(c.x(), c.y() - 3.2 * k))
        painter.end()


class Status(QWidget):
    """Icon + text, e.g. (check) Resolved."""

    def __init__(self, state: str, text: str | None = None, style: str = "body",
                 size: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.icon = StatusIcon(state, size)
        self.label = Text(text if text is not None else STATUS_TEXT.get(state, state), style)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

    def set(self, state: str, text: str | None = None) -> None:
        self.icon.set_state(state)
        self.label.setText(text if text is not None else STATUS_TEXT.get(state, state))


class ProgressRing(StatusIcon):
    def __init__(self, size: int = 16, parent: QWidget | None = None) -> None:
        super().__init__("running", size, parent)


class ProgressBar(QWidget):
    """Determinate (value 0..1) or indeterminate progress bar."""

    def __init__(self, parent: QWidget | None = None, *, meter: bool = False) -> None:
        super().__init__(parent)
        self._value: float | None = 0.0
        self._offset = 0.0
        self._meter = meter  # meters (evidence cards) use a thicker filled track
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setFixedHeight(4 if meter else 3)
        self.setMinimumWidth(40)

    def set_value(self, value: float | None) -> None:
        self._value = None if value is None else max(0.0, min(1.0, value))
        if self._value is None:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._offset = (self._offset + 16 / motion.PROGRESS_LOOP_MS) % 1.4
        self.update()

    def paintEvent(self, _event) -> None:
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        if self._meter:
            painter.setPen(Qt.PenStyle.NoPen)
            track = QColor(p.text_secondary)
            track.setAlphaF(0.22)
            painter.setBrush(track)
            painter.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        else:
            line = QColor(p.strong_stroke)
            painter.setPen(QPen(line, 1))
            painter.drawLine(QPointF(0, h / 2), QPointF(w, h / 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.accent))
        if self._value is None:
            start = (self._offset - 0.4) * w
            painter.drawRoundedRect(QRectF(max(0.0, start), 0, min(w * 0.4, w - max(0.0, start)),
                                           h), h / 2, h / 2)
        elif self._value > 0:
            painter.drawRoundedRect(QRectF(0, 0, max(h, w * self._value), h), h / 2, h / 2)
        painter.end()


class InfoBar(QFrame):
    """Severity message bar: informational, success, caution or critical."""

    closed = Signal()
    _BG = {"info": "info_bg", "success": "success_bg", "caution": "caution_bg",
           "critical": "critical_bg"}

    def __init__(self, severity: str, title: str, message: str = "",
                 action: str | None = None, closable: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.severity = severity
        self.setObjectName("InfoBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(12)
        state = {"info": "info", "success": "success", "caution": "caution",
                 "critical": "critical"}[severity]
        layout.addWidget(StatusIcon(state, 16), 0, Qt.AlignmentFlag.AlignTop)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.title = Text(title, "body_strong")
        self.message = Text(message, "body", wrap=True)
        row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignTop)
        if message:
            row.addWidget(self.message, 1)
        else:
            row.addStretch(1)
        text_col.addLayout(row)
        layout.addLayout(text_col, 1)
        self.action_button = None
        if action:
            self.action_button = Button(action, "Standard")
            layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignVCenter)
        if closable:
            close = Button("", "Subtle", icon="close")
            close.setFixedWidth(32)
            close.setAccessibleName("Close")
            close.clicked.connect(self._close)
            layout.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self._restyle()
        theme.manager().changed.connect(self._restyle)
        self.setAccessibleName(f"{title} {message}".strip())

    def _close(self) -> None:
        self.hide()
        self.closed.emit()

    def _restyle(self, _palette=None) -> None:
        p = theme.palette()
        bg = getattr(p, self._BG[self.severity])
        self.setStyleSheet(f"QFrame#InfoBar {{ background: {bg}; border: 1px solid "
                           f"{p.card_border}; border-radius: 4px; }}")
