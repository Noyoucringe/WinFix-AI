"""The main window: title bar, navigation pane and a Mica-style layer of pages."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPlainTextEdit,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.core.history import HistoryStore
from app.core.logging_setup import get_logger
from app.core.user_settings import get_store
from app.gui import chrome, motion, theme
from app.gui.branding import app_icon
from app.gui.controller import TroubleshootController
from app.gui.pages.about import AboutPage
from app.gui.pages.base import AppContext, Page
from app.gui.pages.diagnostics import DiagnosticsPage
from app.gui.pages.history import HistoryDetailPage, HistoryPage
from app.gui.pages.home import HomePage
from app.gui.pages.settings import AIProviderPage, PrivacyPage, SettingsPage
from app.gui.pages.troubleshoot import TroubleshootPage
from app.gui.widgets.composite import Expander
from app.gui.widgets.dialog import ContentDialog
from app.gui.widgets.navigation import NavigationPane, TitleBar
from app.gui.widgets.status import InfoBar

logger = get_logger(__name__)

PAGES: dict[str, type[Page]] = {
    "home": HomePage,
    "troubleshoot": TroubleshootPage,
    "history": HistoryPage,
    "history_detail": HistoryDetailPage,
    "diagnostics": DiagnosticsPage,
    "settings": SettingsPage,
    "settings_ai": AIProviderPage,
    "settings_privacy": PrivacyPage,
    "about": AboutPage,
}
COMPACT_BELOW = 1000
MAX_BACK = 30


def frameless() -> bool:
    return chrome.use_custom_frame() or os.environ.get("WINFIX_FRAMELESS") == "1"


class Toast(QWidget):
    """A short in-app confirmation shown at the bottom of the page layer."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, title: str, message: str, severity: str = "success") -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        bar = InfoBar(severity, title, message, closable=True)
        bar.closed.connect(self.hide)
        self._layout.addWidget(bar)
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(5000)

    def reposition(self) -> None:
        parent = self.parentWidget()
        width = min(560, parent.width() - 48)
        self.setFixedWidth(width)
        self.adjustSize()
        self.move((parent.width() - width) // 2, parent.height() - self.height() - 24)


class MainWindow(QWidget):
    def __init__(self, history: HistoryStore | None = None, demo=None) -> None:
        super().__init__(None, chrome.frameless_flags() if frameless() else
                         Qt.WindowType.Window)
        self.setWindowTitle("WinFix AI")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(760, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self.history = history or HistoryStore()
        self.controller = TroubleshootController(self.history, self)
        self.controller.demo = demo
        self.ctx = AppContext(window=self, history=self.history,
                              controller=self.controller, demo=demo)
        self._pages: dict[str, Page] = {}
        self._current: tuple[str, dict] | None = None
        self._back: list[tuple[str, dict]] = []
        self._user_compact: bool | None = None
        self._tray: QSystemTrayIcon | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_bar = TitleBar(self, caption_buttons=frameless())
        self.title_bar.back.connect(self.go_back)
        self.title_bar.minimize.connect(self.showMinimized)
        self.title_bar.toggle_maximize.connect(self._toggle_maximize)
        self.title_bar.close.connect(self.close)
        root.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = NavigationPane(self)
        self.nav.selected.connect(self._nav_selected)
        self.nav.menu.clicked.connect(lambda: setattr(self, "_user_compact",
                                                      self.nav.is_compact()))
        nav_host = QVBoxLayout()
        nav_host.setContentsMargins(4, 0, 4, 0)
        nav_host.addWidget(self.nav)
        body.addLayout(nav_host)

        self.layer = QWidget()
        self.layer.setObjectName("Layer")
        self.layer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layer_layout = QVBoxLayout(self.layer)
        layer_layout.setContentsMargins(1, 1, 0, 0)
        layer_layout.setSpacing(0)
        if demo is not None:
            from app.demo import BANNER

            banner = InfoBar("caution", "Demo mode", BANNER)
            banner.setAccessibleName("Demo mode. " + BANNER)
            host = QWidget()
            hl = QVBoxLayout(host)
            hl.setContentsMargins(40, 16, 40, 0)
            hl.addWidget(banner)
            layer_layout.addWidget(host)
        self.stack = QStackedWidget()
        layer_layout.addWidget(self.stack, 1)
        body.addWidget(self.layer, 1)
        root.addLayout(body, 1)

        self.toast = Toast(self.layer)
        self.layer.installEventFilter(self)

        QShortcut(QKeySequence(Qt.Modifier.ALT | Qt.Key.Key_Left), self, self.go_back)
        QShortcut(QKeySequence(Qt.Key.Key_Back), self, self.go_back)
        QShortcut(QKeySequence("Ctrl+N"), self, lambda: self.navigate("home"))
        QShortcut(QKeySequence("Ctrl+H"), self, lambda: self.navigate("history"))
        QShortcut(QKeySequence("Ctrl+,"), self, lambda: self.navigate("settings"))

        theme.manager().changed.connect(self._theme_changed)
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._system_theme_changed)
        self._restore_geometry()
        self.navigate("home", _record=False)
        self.title_bar.set_back_enabled(False)

    # --- pages ------------------------------------------------------------
    def page(self, key: str) -> Page:
        if key not in self._pages:
            page = PAGES[key](self.ctx)
            self._pages[key] = page
            self.stack.addWidget(page)
        return self._pages[key]

    def navigate(self, key: str, _record: bool = True, **params) -> None:
        if key not in PAGES:
            logger.warning("unknown page", extra={"component": "gui", "event": key})
            return
        if self._current and _record:
            if self._current[0] != key or self._current[1] != params:
                self._back.append(self._current)
                del self._back[:-MAX_BACK]
        previous = self.stack.currentWidget()
        if isinstance(previous, Page) and previous.key != key:
            previous.on_hide()
        page = self.page(key)
        self._current = (key, params)
        self.stack.setCurrentWidget(page)
        self.nav.set_current(page.nav_key or key)
        self.title_bar.set_back_enabled(bool(self._back))
        page.on_show(**params)
        motion.page_entrance(page.column)
        page.setFocus()

    def current_key(self) -> str | None:
        return self._current[0] if self._current else None

    def go_back(self) -> None:
        if not self._back:
            return
        key, params = self._back.pop()
        self.navigate(key, _record=False, **params)

    def _nav_selected(self, key: str) -> None:
        self.navigate(key)

    # --- messages ---------------------------------------------------------
    def show_error(self, title: str, message: str, detail: str = "") -> None:
        dialog = ContentDialog(self, title, message, primary="Close",
                               secondary="Copy details" if detail else "")
        if not detail:
            dialog.secondary.hide()
        else:
            expander = Expander("document", "Technical details",
                                "Useful if you report this problem")
            text = QPlainTextEdit(detail)
            text.setReadOnly(True)
            text.setFixedHeight(160)
            expander.content_layout.setContentsMargins(16, 12, 16, 16)
            expander.content_layout.addWidget(text)
            dialog.body.addWidget(expander)

        def done(accepted: bool) -> None:
            if not accepted and detail:
                QGuiApplication.clipboard().setText(detail)
        dialog.open_async(done)

    def notify(self, title: str, message: str) -> None:
        """In-app toast when WinFix is in front; a Windows notification otherwise."""
        if self.isActiveWindow() or not get_store().load().notifications:
            self.toast.show_message(title, message)
            return
        if QSystemTrayIcon.isSystemTrayAvailable():
            if self._tray is None:
                self._tray = QSystemTrayIcon(app_icon(), self)
                self._tray.setToolTip("WinFix AI")
                self._tray.messageClicked.connect(self._bring_to_front)
                self._tray.activated.connect(lambda _r: self._bring_to_front())
            self._tray.show()
            self._tray.showMessage(title, message, app_icon(), 6000)
        else:
            QApplication.alert(self)
        self.toast.show_message(title, message)

    def _bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    # --- theme ------------------------------------------------------------
    def _theme_changed(self, palette) -> None:
        chrome.set_dark(self, palette.name == "dark")
        self.update()

    def _system_theme_changed(self, *_args) -> None:
        if theme.manager().mode == "system":
            theme.manager().apply("system")

    def paintEvent(self, _event) -> None:
        # Mica-style base: a soft, desktop-tinted gradient under the layer.
        p = theme.palette()
        painter = QPainter(self)
        gradient = QLinearGradient(QPointF(0, 0), QPointF(self.width(), self.height()))
        gradient.setColorAt(0.0, QColor(p.mica_start))
        gradient.setColorAt(1.0, QColor(p.mica_end))
        painter.fillRect(self.rect(), gradient)
        painter.end()

    # --- window behaviour -------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_chrome_installed", False):
            self._chrome_installed = True
            if chrome.use_custom_frame():
                chrome.install(self)
            chrome.set_dark(self, theme.palette().name == "dark")

    def nativeEvent(self, event_type, message):
        if chrome.use_custom_frame() and event_type == b"windows_generic_MSG":
            handled, result = chrome.handle_native_event(self, self.title_bar, message)
            if handled:
                return True, result
        return super().nativeEvent(event_type, message)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def _toggle_maximize(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._user_compact is None:
            self.nav.set_compact(self.width() < COMPACT_BELOW)
        elif self.width() < COMPACT_BELOW and not self.nav.is_compact():
            self.nav.set_compact(True)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.layer and event.type() == QEvent.Type.Resize and self.toast.isVisible():
            self.toast.reposition()
        return False

    def _restore_geometry(self) -> None:
        saved = get_store().load().window or {}
        width, height = saved.get("w", 1180), saved.get("h", 800)
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
        width, height = min(width, area.width()), min(height, area.height())
        x = saved.get("x", area.x() + (area.width() - width) // 2)
        y = saved.get("y", area.y() + (area.height() - height) // 2)
        rect = QRect(x, y, width, height)
        if not any(s.availableGeometry().intersects(rect)
                   for s in QGuiApplication.screens()):
            rect.moveCenter(area.center())
        self.setGeometry(rect)
        self._start_maximized = bool(saved.get("maximized"))

    def _save_geometry(self) -> None:
        geo = self.normalGeometry() if self.isMaximized() else self.geometry()
        try:
            get_store().update(window={"x": geo.x(), "y": geo.y(), "w": geo.width(),
                                       "h": geo.height(), "maximized": self.isMaximized()})
        except OSError:
            pass

    def closeEvent(self, event) -> None:
        if self.controller.state == "applying" and not getattr(self, "_force_close", False):
            event.ignore()
            dialog = ContentDialog(self, "A fix is still being applied",
                                   "Closing WinFix now won't undo the change, but WinFix "
                                   "won't be able to check whether it worked. Wait for it "
                                   "to finish?", primary="Keep WinFix open",
                                   secondary="Close anyway")

            def done(keep_open: bool) -> None:
                if not keep_open:
                    self._force_close = True
                    self.close()
            dialog.open_async(done)
            return
        self.controller.cancel()
        current = self.stack.currentWidget()
        if isinstance(current, Page):
            current.on_hide()
        self._save_geometry()
        if self._tray is not None:
            self._tray.hide()
        super().closeEvent(event)
