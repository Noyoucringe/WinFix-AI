"""Application bootstrap: GUI, demo mode, self-test and sign-in health check."""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication

from app import APP_NAME, ENGINE_VERSION, PUBLISHER, __version__
from app.core.logging_setup import get_logger

logger = get_logger(__name__)

PAGE_KEYS = ["home", "troubleshoot", "history", "diagnostics", "settings", "settings_ai",
             "settings_privacy", "about"]
_errors: list[str] = []


# --- application -------------------------------------------------------------------
def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is not None:
        return app
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(PUBLISHER)
    QCoreApplication.setApplicationVersion(__version__)
    if sys.platform == "win32":
        try:  # own taskbar group and icon instead of python.exe's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "WinFixAI.WinFixAI.1")
        except (AttributeError, OSError):
            pass
    app = QApplication(argv if argv is not None else sys.argv[:1])
    app.setStyle("Fusion")  # neutral base; the Fluent look comes from the theme
    from app.gui.branding import app_icon
    from app.gui.widgets.core import font

    app.setWindowIcon(app_icon())
    base = font("body")
    base.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(base)
    return app


def _install_excepthook(show_dialog: Callable[[str, str], None] | None) -> None:
    """Uncaught errors in slots are logged and shown, never silently lost."""

    def hook(exc_type, exc, tb) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        _errors.append(detail)
        logger.error("unhandled exception", extra={"component": "gui",
                                                   "status": exc_type.__name__})
        if show_dialog is not None:
            try:
                show_dialog(str(exc) or exc_type.__name__, detail)
            except Exception:  # noqa: BLE001 - never recurse
                pass

    sys.excepthook = hook


def _apply_theme() -> None:
    from app.core.user_settings import get_store
    from app.gui import theme

    theme.manager().apply(get_store().load().theme)


def run_gui(*, demo: bool = False) -> int:
    from app.core.history import HistoryStore

    demo_mode = None
    if demo:
        from app.demo import DemoMode, isolate, seed_history

        isolate()
        _reset_stores()
    app = create_application()
    _apply_theme()
    history = HistoryStore()
    if demo:
        from app.core.tool_registry import get_registry

        demo_mode = DemoMode(get_registry())
        seed_history(demo_mode, history)
    from app.gui.window import MainWindow

    window = MainWindow(history=history, demo=demo_mode)
    _install_excepthook(lambda m, d: window.show_error(
        "Something went wrong", "WinFix ran into an unexpected problem. You can keep "
        "using the app.", d))
    if getattr(window, "_start_maximized", False):
        window.showMaximized()
    else:
        window.show()
    logger.info("gui started", extra={"component": "gui",
                                      "event": "demo" if demo else "start"})
    return app.exec()


def _reset_stores() -> None:
    from app.core import user_settings
    from app.core.config import get_settings

    get_settings.cache_clear()
    user_settings.set_store(None)


# --- health check -----------------------------------------------------------------
def run_health_check() -> int:
    """Sign-in check: notify only when something needs attention, then exit."""
    from app.core.health import run_health_check as check
    from app.core.user_settings import get_store

    report = check()
    if not report.needs_attention or not get_store().load().notifications:
        return 0
    app = create_application()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QSystemTrayIcon

    from app.gui.branding import app_icon

    if not QSystemTrayIcon.isSystemTrayAvailable():
        return 0
    tray = QSystemTrayIcon(app_icon())
    tray.setToolTip(APP_NAME)
    tray.show()

    def open_app() -> None:
        tray.hide()
        import subprocess

        from app.core import autostart

        exe = autostart.command().replace(" --health-check", "")
        subprocess.Popen(exe, close_fds=True)  # noqa: S603 - our own executable
        app.quit()

    tray.messageClicked.connect(open_app)
    tray.activated.connect(lambda _r: open_app())
    detail = "; ".join(report.findings) or report.headline
    tray.showMessage("WinFix AI found something to look at",
                     f"{detail} Open WinFix to troubleshoot.", app_icon(), 15000)
    QTimer.singleShot(60000, app.quit)
    return app.exec()


# --- self-test -------------------------------------------------------------------
@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    seconds: float = 0.0


class SelfTest:
    """Drives the real UI in demo mode (isolated data, simulated fixes)."""

    def __init__(self, screenshots: Path | None) -> None:
        self.screenshots = screenshots
        self.checks: list[Check] = []
        self.window = None

    # helpers
    def pump(self, ms: int = 50) -> None:
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            QApplication.processEvents()
            time.sleep(0.01)

    def wait(self, predicate: Callable[[], bool], timeout: float = 90.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            QApplication.processEvents()
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def settle(self) -> None:
        from app.gui.workers import wait_for_idle

        for _ in range(3):
            self.pump(120)
            wait_for_idle(20000)
        self.pump(400)  # page entrance animation

    def shot(self, name: str) -> None:
        if self.screenshots is None:
            return
        self.screenshots.mkdir(parents=True, exist_ok=True)
        self.window.grab().save(str(self.screenshots / f"{name}.png"))

    def check(self, name: str, fn: Callable[[], str | None]) -> None:
        start = time.monotonic()
        before = len(_errors)
        try:
            detail = fn() or ""
            passed = len(_errors) == before
            if not passed:
                detail = (detail + " Unhandled error: " + _errors[-1].strip().splitlines()[-1]
                          ).strip()
        except Exception as exc:  # noqa: BLE001 - recorded as a failed check
            passed, detail = False, f"{type(exc).__name__}: {exc}"
            _errors.append(traceback.format_exc())
        self.checks.append(Check(name, passed, detail, round(time.monotonic() - start, 2)))
        logger.info("self-test check", extra={"component": "selftest", "event": name,
                                              "status": "pass" if passed else "fail"})

    # steps
    def run(self) -> list[Check]:
        from app.core.history import HistoryStore
        from app.core.tool_registry import get_registry
        from app.demo import DemoMode, seed_history
        from app.gui import theme
        from app.gui.window import MainWindow

        demo = DemoMode(get_registry())
        history = HistoryStore()

        def start_window() -> str:
            seed_history(demo, history)
            self.window = MainWindow(history=history, demo=demo)
            self.window.resize(1280, 860)
            self.window.show()
            self.settle()
            return f"{history.count()} sample sessions"

        self.check("Main window opens", start_window)
        if self.window is None:
            return self.checks
        registry = get_registry()
        self.check("Tool registry loaded", lambda: (
            f"{len(registry.diagnostic_names())} read-only checks, "
            f"{len(registry.remediation_names())} approved fixes"
            if len(registry.diagnostic_names()) >= 20 else _fail("too few diagnostics")))

        for mode in ("light", "dark"):
            theme.manager().apply(mode)
            for key in PAGE_KEYS:
                def visit(key=key, mode=mode) -> str:
                    self.window.navigate(key)
                    self.settle()
                    if self.window.current_key() != key:
                        _fail(f"expected page {key}")
                    self.shot(f"{mode}_{key}")
                    return ""
                self.check(f"Page {key} ({mode})", visit)
            self.check(f"History detail ({mode})", lambda mode=mode: self._history_detail(mode))
        theme.manager().apply("light")
        self.check("Troubleshooting flow: diagnose", self._diagnose)
        self.check("Troubleshooting flow: approve and verify", self._approve)
        self.check("Compact navigation below 1000 px", self._compact)
        self.check("Every page fits a 1000 px window", lambda: self._fits(1000, 720))
        self.check("Every page fits the minimum window size", lambda: self._fits(760, 560))
        self.window._force_close = True
        self.window.close()
        return self.checks

    def _history_detail(self, mode: str) -> str:
        rows = self.window.history.list_sessions(limit=1)
        if not rows:
            _fail("no history")
        self.window.navigate("history_detail", session_id=rows[0]["id"])
        self.settle()
        self.shot(f"{mode}_history_detail")
        return rows[0]["problem"]

    def _diagnose(self) -> str:
        w = self.window
        w.navigate("home")
        self.settle()
        home = w.page("home")
        home.problem.input.setText("My laptop is very slow")
        home.problem.submit()
        self.pump(600)
        self.shot("flow_1_investigating")
        if not self.wait(lambda: w.controller.state in ("diagnosed", "error", "cancelled")):
            _fail("diagnosis timed out")
        if w.controller.state != "diagnosed":
            _fail(f"state {w.controller.state}")
        self.settle()
        self.shot("flow_2_diagnosis")
        session = w.controller.session
        if not session.proposals:
            _fail("no fix proposed")
        page = w.page("troubleshoot")
        page.show_view("fix")
        self.settle()
        self.shot("flow_3_fix")
        return session.diagnosis.headline

    def _approve(self) -> str:
        w = self.window
        page = w.page("troubleshoot")
        proposal = w.controller.session.proposals[0]
        page._confirm(proposal)
        self.settle()
        self.shot("flow_4_approval")
        page._dialog.primary.click()  # the user's approval
        self.pump(300)
        self.shot("flow_5_applying")
        if not self.wait(lambda: w.controller.state in ("result", "error")):
            _fail("verification timed out")
        if w.controller.state != "result":
            _fail(f"state {w.controller.state}")
        self.settle()
        self.shot("flow_6_result")
        session = w.controller.session
        stored = w.history.get_session(session.id)
        if not stored:
            _fail("session not saved to history")
        verification = session.verification
        if verification is None or not verification.improved:
            _fail("verification did not report an improvement")
        return f"{proposal.title}: {verification.headline}"

    def _fits(self, width: int, height: int) -> str:
        """No page may be wider than its visible area (content would be clipped)."""
        from PySide6.QtGui import QFontDatabase

        if not QFontDatabase.families():
            # e.g. Qt's offscreen platform on Windows: no fonts are loaded and
            # text is measured with placeholder metrics, so widths mean nothing.
            return "skipped: this Qt platform has no fonts to measure text with"
        w = self.window
        w.resize(width, height)
        self.settle()
        too_wide = []
        troubleshoot_views = ("start", "diagnosis", "fix", "result")
        for key in PAGE_KEYS + ["history_detail"] + [f"troubleshoot:{v}"
                                                      for v in troubleshoot_views]:
            if key.startswith("troubleshoot:"):
                w.navigate("troubleshoot")
                w.page("troubleshoot").show_view(key.split(":")[1])
                page = w.page("troubleshoot")
            elif key == "history_detail":
                rows = w.history.list_sessions(limit=1)
                w.navigate(key, session_id=rows[0]["id"])
                page = w.page(key)
            else:
                w.navigate(key)
                page = w.page(key)
            self.settle()
            self.shot(f"size{width}_{key.replace(':', '_')}")
            need = page.column.minimumSizeHint().width()
            have = page.scroll.viewport().width()
            if need > have:
                too_wide.append(f"{key} needs {need} px, has {have} px")
        w.resize(1280, 860)
        self.settle()
        if too_wide:
            _fail("; ".join(too_wide))
        return f"{width}x{height}"

    def _compact(self) -> str:
        w = self.window
        w.navigate("home")
        w.resize(900, 700)
        self.settle()
        if not w.nav.is_compact():
            _fail("navigation did not collapse")
        self.shot("compact_home")
        w.resize(1280, 860)
        self.settle()
        return ""


def _fail(message: str):
    raise AssertionError(message)


def run_self_test(report: Path | None = None, screenshots: Path | None = None,
                  offscreen: bool = False) -> int:
    """``--self-test``: exercise every page and the full flow; write a report."""
    if offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["WINFIX_REDUCED_MOTION"] = "1"  # deterministic screenshots
    folder = Path(tempfile.mkdtemp(prefix="winfix-selftest-"))
    os.environ["WINFIX_DATA_DIR"] = str(folder)
    _reset_stores()
    started = time.monotonic()
    app = create_application()
    _apply_theme()
    _install_excepthook(None)
    test = SelfTest(screenshots)
    try:
        checks = test.run()
    except Exception as exc:  # noqa: BLE001 - a crash is a failed self-test
        _errors.append(traceback.format_exc())
        checks = test.checks + [Check("Self-test run", False, f"{type(exc).__name__}: {exc}")]
    app.processEvents()
    passed = sum(c.passed for c in checks)
    lines = [
        f"{APP_NAME} self-test",
        f"Version: {__version__} (diagnostics engine {ENGINE_VERSION})",
        f"Executable: {sys.executable}",
        f"Frozen: {bool(getattr(sys, 'frozen', False))}",
        f"OS: {platform.platform()}",
        f"Qt platform: {QGuiApplication.platformName()}",
        f"Isolated data folder: {folder}",
        f"Duration: {time.monotonic() - started:.1f} s",
        f"Result: {passed}/{len(checks)} checks passed",
        "",
    ]
    for c in checks:
        lines.append(f"[{'PASS' if c.passed else 'FAIL'}] {c.name} ({c.seconds:.1f} s)"
                     + (f" - {c.detail}" if c.detail else ""))
    if _errors:
        lines += ["", "Unhandled errors:"] + _errors
    text = "\n".join(lines) + "\n"
    target = report or folder / "self_test_report.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    target.with_suffix(".json").write_text(json.dumps(
        {"version": __version__, "passed": passed, "total": len(checks),
         "checks": [asdict(c) for c in checks], "errors": _errors}, indent=2),
        encoding="utf-8")
    if sys.stdout is not None:
        try:
            print(text)
        except (OSError, ValueError):
            pass
    return 0 if passed == len(checks) and not _errors else 1
