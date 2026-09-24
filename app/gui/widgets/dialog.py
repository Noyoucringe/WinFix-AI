"""ContentDialog: an acrylic-style dialog over a smoke layer.

Commit button first (as in Windows), Esc cancels, focus stays inside the
dialog, and it scales from 1.05 to 1 over 250 ms (skipped with reduced
motion). ``exec()`` blocks with a local event loop and returns True only
when the commit button was pressed.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QEventLoop, QPropertyAnimation, QRect, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from app.gui import motion, theme
from app.gui.widgets.core import Button, Text


class _Smoke(QWidget):
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        color = QColor(0, 0, 0, 102 if theme.palette().name == "dark" else 77)
        painter.fillRect(self.rect(), color)
        painter.end()


class ContentDialog(QWidget):
    def __init__(self, parent: QWidget, title: str, message: str = "",
                 primary: str = "OK", secondary: str = "Cancel",
                 primary_icon: str | None = None, width: int = 500) -> None:
        super().__init__(parent)
        self._result = False
        self._loop: QEventLoop | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.smoke = _Smoke(self)
        self.panel = QFrame(self)
        self.panel.setObjectName("DialogPanel")
        self.panel.setFixedWidth(width)
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.panel.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self.panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body_host = QWidget()
        self.body = QVBoxLayout(body_host)
        self.body.setContentsMargins(24, 24, 24, 20)
        self.body.setSpacing(12)
        self.title = Text(title, "subtitle")
        self.body.addWidget(self.title)
        if message:
            self.body.addWidget(Text(message, "body", wrap=True))
        outer.addWidget(body_host)

        self.footer = QFrame()
        self.footer.setObjectName("DialogFooter")
        foot = QHBoxLayout(self.footer)
        foot.setContentsMargins(24, 24, 24, 24)
        foot.setSpacing(8)
        self.primary = Button(primary, "Accent", primary_icon)
        self.secondary = Button(secondary, "Standard")
        self.primary.clicked.connect(lambda: self.done(True))
        self.secondary.clicked.connect(lambda: self.done(False))
        foot.addWidget(self.primary, 1)
        foot.addWidget(self.secondary, 1)
        outer.addWidget(self.footer)

        self._restyle()
        theme.manager().changed.connect(self._restyle)
        self.setAccessibleName(title)
        parent.installEventFilter(self)

    def _restyle(self, _palette=None) -> None:
        p = theme.palette()
        self.panel.setStyleSheet(
            f"QFrame#DialogPanel {{ background: {p.dialog}; border: 1px solid "
            f"{p.card_border}; border-radius: 8px; }}"
            f"QFrame#DialogFooter {{ background: {p.dialog_footer}; border: none;"
            f" border-top: 1px solid {p.card_border}; border-bottom-left-radius: 8px;"
            f" border-bottom-right-radius: 8px; }}")

    # --- geometry ---------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self._layout()
        return False

    def _layout(self) -> None:
        parent = self.parentWidget()
        self.setGeometry(parent.rect())
        self.smoke.setGeometry(self.rect())
        self.panel.adjustSize()
        size = self.panel.sizeHint()
        self.panel.setGeometry(QRect((self.width() - self.panel.width()) // 2,
                                     (self.height() - size.height()) // 2,
                                     self.panel.width(), size.height()))

    # --- running --------------------------------------------------------
    def exec(self) -> bool:
        self._layout()
        self.show()
        self.raise_()
        self._animate_in()
        self.primary.setFocus()
        self._loop = QEventLoop(self)
        self._loop.exec()
        return self._result

    def open_async(self, callback) -> None:
        """Non-blocking variant: calls ``callback(accepted)`` when closed."""
        self._callback = callback
        self._layout()
        self.show()
        self.raise_()
        self._animate_in()
        self.primary.setFocus()

    def _animate_in(self) -> None:
        if not motion.animations_enabled():
            return
        end = self.panel.geometry()
        dw, dh = int(end.width() * 0.025), int(end.height() * 0.025)
        start = end.adjusted(-dw, -dh, dw, dh)
        anim = QPropertyAnimation(self.panel, b"geometry", self)
        anim.setDuration(motion.DIALOG_MS)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim

    def done(self, accepted: bool) -> None:
        self._result = accepted
        self.hide()
        if self._loop is not None:
            self._loop.quit()
        callback = getattr(self, "_callback", None)
        if callback:
            self._callback = None
            callback(accepted)
        self.parent().removeEventFilter(self)
        self.deleteLater()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.done(False)
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, forward: bool) -> bool:
        # Keep keyboard focus inside the dialog.
        order = [w for w in self.panel.findChildren(QWidget)
                 if w.focusPolicy() & Qt.FocusPolicy.TabFocus and w.isVisible()]
        if not order:
            return True
        current = order.index(self.focusWidget()) if self.focusWidget() in order else -1
        order[(current + (1 if forward else -1)) % len(order)].setFocus()
        return True
