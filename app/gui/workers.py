"""Background execution for the GUI.

Anything that can take time — diagnostics, contacting an LLM, a fix,
verification, loading history — runs on a worker thread so the window never
freezes. Results come back to the UI thread through Qt signals.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.core.logging_setup import get_logger

logger = get_logger(__name__)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str, str)  # user message, technical detail


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any], signals: _Signals) -> None:
        super().__init__()
        self.fn = fn
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001 - reported to the UI, not swallowed
            detail = traceback.format_exc()
            logger.error("background task failed",
                         extra={"component": "gui", "event": "task_failed",
                                "status": type(exc).__name__})
            self.signals.failed.emit(str(exc) or type(exc).__name__, detail)
            return
        self.signals.done.emit(result)


_pool = QThreadPool()
_pool.setMaxThreadCount(4)
_live: set[_Signals] = set()


def run_async(fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None,
              on_error: Callable[[str, str], None] | None = None) -> None:
    """Run ``fn`` on a worker thread; callbacks run on the UI thread."""
    signals = _Signals()
    _live.add(signals)  # keep the QObject alive until a result arrives

    def finish(*_args) -> None:
        _live.discard(signals)

    if on_done:
        signals.done.connect(on_done)
    if on_error:
        signals.failed.connect(on_error)
    signals.done.connect(finish)
    signals.failed.connect(finish)
    _pool.start(_Task(fn, signals))


def wait_for_idle(msecs: int = 30000) -> bool:
    return _pool.waitForDone(msecs)
