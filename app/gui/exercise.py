"""Self-test helper: operate every control on a page, the way a user would.

Used by ``--self-test``. Everything that would reach outside the app is
replaced for the duration of the test (see :func:`sandbox`): file dialogs
save into a temporary folder, "open folder" does nothing, API keys stay in
memory, "Start with Windows" is not written, and AI requests are not sent.
Dialogs that open are cancelled, so destructive actions (Clear history,
Remove key, Apply fix) are never confirmed here.
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QLineEdit,
    QWidget,
)


@contextlib.contextmanager
def sandbox(folder: Path):
    """Replace every outward-facing side effect for the duration of the test."""
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QFileDialog

    from app.core import autostart, credentials
    from app.llm import provider

    folder.mkdir(parents=True, exist_ok=True)
    enabled = {"on": False}
    saved = {
        (QFileDialog, "getSaveFileName"): QFileDialog.getSaveFileName,
        (QDesktopServices, "openUrl"): QDesktopServices.openUrl,
        (autostart, "set_enabled"): autostart.set_enabled,
        (autostart, "is_enabled"): autostart.is_enabled,
        (credentials, "_keyring"): credentials._keyring,
        (provider.OpenAICompatibleProvider, "_chat"): provider.OpenAICompatibleProvider._chat,
        (provider.AnthropicProvider, "_chat"): provider.AnthropicProvider._chat,
    }

    def save_file(_parent=None, _caption="", name="", _filter="", *a, **k):
        return str(folder / (Path(name).name or "export.txt")), ""

    def set_autostart(on: bool):
        enabled["on"] = on
        return True, ""

    QFileDialog.getSaveFileName = staticmethod(save_file)
    QDesktopServices.openUrl = staticmethod(lambda _url: True)
    autostart.set_enabled = set_autostart
    autostart.is_enabled = lambda: enabled["on"]
    credentials._keyring = lambda: None  # keys typed in the test stay in memory
    provider.OpenAICompatibleProvider._chat = lambda self, system, user: "OK"
    provider.AnthropicProvider._chat = lambda self, system, user: "OK"
    try:
        yield
    finally:
        for (owner, name), value in saved.items():
            setattr(owner, name, value)
        credentials._session_only.clear()


def _click(widget: QWidget) -> None:
    """A real left click (press + release) in the middle of the widget, delivered
    through the event queue like input from the mouse."""
    import shiboken6

    pos = QPointF(widget.width() / 2, widget.height() / 2)
    glob = QPointF(widget.mapToGlobal(pos.toPoint()))
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        if not shiboken6.isValid(widget):
            return  # the press already replaced the page
        event = QMouseEvent(kind, pos, glob, Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress
                            else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        QApplication.postEvent(widget, event)
        QApplication.processEvents()


def _describe(widget: QWidget) -> str:
    text = ""
    for attr in ("text", "accessibleName"):
        with contextlib.suppress(Exception):
            text = text or getattr(widget, attr)()
    return f"{type(widget).__name__} '{(text or '').strip()[:40]}'"


def _custom_click(widget: QWidget) -> bool:
    """App widgets that react to clicks without being buttons (radio rows)."""
    cls = type(widget)
    return (cls.__module__.startswith("app.") and not isinstance(widget, QAbstractButton)
            and cls.mouseReleaseEvent is not QWidget.mouseReleaseEvent)


def controls(page: QWidget) -> list[tuple[str, QWidget]]:
    found = []
    for w in page.findChildren(QWidget):
        if not w.isVisibleTo(page) or not w.isEnabled():
            continue
        if isinstance(w, QAbstractButton):
            found.append(("click", w))
        elif _custom_click(w):
            found.append(("click", w))
        elif isinstance(w, QComboBox):
            found.append(("combo", w))
        elif isinstance(w, QLineEdit) and not w.isReadOnly():
            found.append(("type", w))
    return found


def operate(kind: str, widget: QWidget, settle: Callable[[], None]) -> None:
    if kind == "click":
        _click(widget)
    elif kind == "combo":
        original = widget.currentIndex()
        for i in range(widget.count()):
            with contextlib.suppress(RuntimeError):
                widget.setCurrentIndex(i)
            settle()
        with contextlib.suppress(RuntimeError):
            widget.setCurrentIndex(original)
    elif kind == "type":
        original = widget.text()
        widget.setText("test input")
        widget.editingFinished.emit()
        with contextlib.suppress(RuntimeError):
            widget.returnPressed.emit()
        settle()
        with contextlib.suppress(RuntimeError):
            widget.setText(original)


def close_dialogs(window: QWidget) -> None:
    from app.gui.widgets.dialog import ContentDialog

    for dialog in window.findChildren(ContentDialog):
        if dialog.isVisible():
            dialog.done(False)


class Exerciser:
    """Operates each control of a page once, re-opening the page every time."""

    def __init__(self, window, settle: Callable[[], None], errors: list[str]) -> None:
        self.window = window
        self.settle = settle
        self.errors = errors
        self.dialog_errors: list[str] = []
        original = window.show_error

        def record(title, message, detail=""):
            self.dialog_errors.append(f"{title}: {message}")
            original(title, message, detail)

        window.show_error = record

    def run(self, label: str, open_page: Callable[[], QWidget],
            skip: Callable[[QWidget], bool] = lambda w: False) -> tuple[int, list[str]]:
        page = open_page()
        self.settle()
        total = len(controls(page))
        problems: list[str] = []
        done = 0
        for index in range(total):
            page = open_page()
            self.settle()
            close_dialogs(self.window)
            current = controls(page)
            if index >= len(current):
                break
            kind, widget = current[index]
            if skip(widget):
                continue
            name = _describe(widget)
            before, before_dialogs = len(self.errors), len(self.dialog_errors)
            try:
                operate(kind, widget, self.settle)
            except RuntimeError as exc:
                if "already deleted" not in str(exc):
                    problems.append(f"{name}: {exc}")
            except Exception as exc:  # noqa: BLE001 - reported as a failure
                problems.append(f"{name}: {type(exc).__name__}: {exc}")
            self.settle()
            close_dialogs(self.window)
            if len(self.errors) > before:
                last = self.errors[-1].strip().splitlines()[-1]
                problems.append(f"{name}: {last}")
            if len(self.dialog_errors) > before_dialogs:
                problems.append(f"{name}: error shown - {self.dialog_errors[-1]}")
            done += 1
        return done, [f"{label} > {p}" for p in problems]


def wait_until(predicate: Callable[[], bool], timeout: float = 60.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False
