"""'Start with Windows': a current-user Run entry that launches a quick,
read-only health check at sign-in. WinFix only ever writes its own value."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.core.config import IS_FROZEN
from app.core.logging_setup import get_logger
from app.core.platform_utils import IS_WINDOWS

logger = get_logger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WinFix AI"
HEALTH_CHECK_FLAG = "--health-check"


def supported() -> bool:
    return IS_WINDOWS


def command() -> str:
    if IS_FROZEN:
        return subprocess.list2cmdline([sys.executable, HEALTH_CHECK_FLAG])
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else sys.executable)
    return subprocess.list2cmdline([exe, "-m", "app.main", HEALTH_CHECK_FLAG])


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> tuple[bool, str]:
    """Add or remove WinFix's own Run entry. Returns (ok, message)."""
    if not supported():
        return False, "Starting with Windows is only available on Windows."
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        logger.warning("autostart change failed", extra={"component": "autostart",
                                                         "status": type(exc).__name__})
        return False, "Windows didn't allow this change."
    logger.info("autostart updated", extra={"component": "autostart",
                                            "event": "enabled" if enabled else "disabled"})
    return True, ""
