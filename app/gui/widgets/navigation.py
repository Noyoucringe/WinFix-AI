"""Window chrome: navigation pane and title bar."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.gui import icons, motion, theme
from app.gui.branding import app_icon
from app.gui.widgets.core import Button, font

NAV_WIDTH = 264
NAV_COMPACT_WIDTH = 48


class NavItem(QAbstractButton):
    def __init__(self, key: str, text: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key, self._text, self._icon = key, text, icon
        self.compact = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(40)
        self.setFont(font("body"))
        self.setAccessibleName(text)
        self.setToolTip(text)

    def sizeHint(self) -> QSize:
        return QSize(200, 40)

    def paintEvent(self, _event) -> None:
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(4, 2, self.width() - 8, self.height() - 4)
        if self.isChecked():
            painter.setBrush(QColor(_rgba(p.nav_selected)))
        elif self.underMouse():
            painter.setBrush(QColor(_rgba(p.nav_hover)))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)
        if self.hasFocus() and self.focusPolicy() != Qt.FocusPolicy.NoFocus:
            painter.setPen(QPen(QColor(p.focus), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
        pm = icons.pixmap(self._icon, QColor(p.text).name(), 16, self.devicePixelRatioF())
        painter.drawPixmap(16, (self.height() - 16) // 2, pm)
        if not self.compact:
            painter.setPen(QColor(p.text))
            painter.setFont(self.font())
            painter.drawText(QRect(48, 0, self.width() - 56, self.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             self._text)
        painter.end()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


def _rgba(value: str) -> QColor:
    if value.startswith("rgba"):
        r, g, b, a = [float(x) for x in value[5:-1].split(",")]
        return QColor(int(r), int(g), int(b), int(a * 255))
    return QColor(value)


class _Pill(QWidget):
    """The 3 x 16 px accent selection indicator."""

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.palette().accent))
        painter.drawRoundedRect(QRectF(0, 0, 3, 16), 1.5, 1.5)
        painter.end()


class NavigationPane(QWidget):
    selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Navigation")
        self._items: dict[str, NavItem] = {}
        self._compact = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(2)

        self.menu = Button("", "Subtle", icon="menu")
        self.menu.setFixedSize(40, 36)
        self.menu.setAccessibleName("Open or close navigation")
        self.menu.clicked.connect(lambda: self.set_compact(not self._compact))
        layout.addWidget(self.menu, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(6)

        top = [("home", "Home", "home"), ("troubleshoot", "Troubleshoot", "troubleshoot"),
               ("history", "History", "history"), ("diagnostics", "Diagnostics", "diagnostics")]
        bottom = [("settings", "Settings", "settings"), ("about", "About WinFix AI", "info")]
        for key, text, icon in top:
            layout.addWidget(self._add(key, text, icon))
        layout.addStretch(1)
        for key, text, icon in bottom:
            layout.addWidget(self._add(key, text, icon))

        self._pill = _Pill(self)
        self._pill.setFixedSize(3, 16)
        self._pill.hide()
        self._anim = QPropertyAnimation(self._pill, b"pos", self)
        self._anim.setDuration(motion.NORMAL_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setFixedWidth(NAV_WIDTH)

    def _add(self, key: str, text: str, icon: str) -> NavItem:
        item = NavItem(key, text, icon, self)
        item.clicked.connect(lambda _=False, k=key: self._on_click(k))
        self._items[key] = item
        return item

    def _on_click(self, key: str) -> None:
        self.set_current(key)
        self.selected.emit(key)

    def set_current(self, key: str) -> None:
        item = self._items.get(key)
        for k, it in self._items.items():
            it.setChecked(k == key)
        if not item:
            self._pill.hide()
            return
        target = item.geometry().topLeft()
        target.setX(4)
        target.setY(item.geometry().top() + (item.height() - 16) // 2)
        if self._pill.isVisible() and motion.animations_enabled():
            self._anim.stop()
            self._anim.setStartValue(self._pill.pos())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._pill.move(target)
            self._pill.show()
        self._pill.raise_()

    def current(self) -> str | None:
        return next((k for k, it in self._items.items() if it.isChecked()), None)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        for item in self._items.values():
            item.compact = compact
            item.update()
        self.setFixedWidth(NAV_COMPACT_WIDTH if compact else NAV_WIDTH)
        self.menu.setAccessibleDescription("Collapsed" if compact else "Expanded")

    def is_compact(self) -> bool:
        return self._compact

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        key = self.current()
        if key:
            item = self._items[key]
            self._pill.move(4, item.geometry().top() + (item.height() - 16) // 2)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        items = list(self._items.values())
        focused = self.focusWidget()
        if focused in items and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            step = -1 if event.key() == Qt.Key.Key_Up else 1
            items[(items.index(focused) + step) % len(items)].setFocus()
            return
        super().keyPressEvent(event)


class TitleBar(QWidget):
    back = Signal()
    minimize = Signal()
    toggle_maximize = Signal()
    close = Signal()

    HEIGHT = 48

    def __init__(self, parent: QWidget | None = None, *, caption_buttons: bool = True) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(0)
        self.back_button = Button("", "Subtle", icon="back")
        self.back_button.setFixedSize(40, 36)
        self.back_button.setAccessibleName("Back")
        self.back_button.setToolTip("Back (Alt+Left)")
        self.back_button.clicked.connect(self.back.emit)
        layout.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(8)
        self._icon = QWidget()
        self._icon.setFixedSize(16, 16)
        self._icon.paintEvent = self._paint_icon
        layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(12)
        from app.gui.widgets.core import Text

        self.title = Text("WinFix AI", "caption")
        layout.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        self.buttons: list[QPushButton] = []
        if caption_buttons:
            for name, icon, signal, label in (
                    ("Caption", "minimize", self.minimize, "Minimize"),
                    ("Caption", "maximize", self.toggle_maximize, "Maximize"),
                    ("Close", "close", self.close, "Close")):
                button = QPushButton()
                button.setObjectName(name)
                button.setFixedSize(46, 32)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setAccessibleName(label)
                button.setToolTip(label)
                button.clicked.connect(signal.emit)
                button._icon_name = icon
                layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
                self.buttons.append(button)
        self._refresh_icons()
        theme.manager().changed.connect(self._refresh_icons)

    def _paint_icon(self, _event) -> None:
        painter = QPainter(self._icon)
        app_icon().paint(painter, self._icon.rect())
        painter.end()

    def _refresh_icons(self, _palette=None) -> None:
        for button in self.buttons:
            button.setIcon(icons.icon(button._icon_name, "text", 16))
            button.setIconSize(QSize(10, 10) if button._icon_name != "close" else QSize(12, 12))

    def set_maximized(self, maximized: bool) -> None:
        if len(self.buttons) == 3:
            self.buttons[1]._icon_name = "restore" if maximized else "maximize"
            self.buttons[1].setAccessibleName("Restore" if maximized else "Maximize")
            self._refresh_icons()

    def set_back_enabled(self, enabled: bool) -> None:
        self.back_button.setEnabled(enabled)

    def caption_button_at(self, pos) -> bool:
        return any(b.geometry().contains(pos) for b in self.buttons) or \
            self.back_button.geometry().contains(pos)

    def mousePressEvent(self, event) -> None:
        # Non-Windows fallback: let the window manager move the window.
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.toggle_maximize.emit()
        super().mouseDoubleClickEvent(event)
