"""System information diagnostics (read-only)."""

from __future__ import annotations

import platform
import socket
import sys
from datetime import datetime, timezone

import psutil

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool

WINDOWS_11_FIRST_BUILD = 22000


def get_system_info() -> ToolResult:
    """Collect basic read-only information about the system."""

    def _impl() -> dict:
        boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
        return {
            "operating_system": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "hostname": socket.gethostname(),
            "boot_time": boot_time.isoformat(),
            "python_version": platform.python_version(),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "memory_total_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1),
        }

    return run_tool("get_system_info", _impl)


def _windows_registry_value(name: str) -> str | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except (ImportError, OSError):
        return None


def get_windows_version() -> ToolResult:
    """Windows product, edition, feature update and build number."""

    def _impl() -> dict:
        if not IS_WINDOWS:
            return {"is_windows": False, "system": platform.system(),
                    "release": platform.release(), "version": platform.version(),
                    "product": f"{platform.system()} {platform.release()}"}
        build = sys.getwindowsversion().build
        # Windows 11 still reports major version 10 (and ProductName "Windows 10"),
        # so the build number is the reliable signal.
        product = "Windows 11" if build >= WINDOWS_11_FIRST_BUILD else "Windows 10"
        edition = platform.win32_edition() or ""
        return {
            "is_windows": True,
            "product": product,
            "edition": edition,
            "display_version": _windows_registry_value("DisplayVersion"),
            "build": build,
            "ubr": _windows_registry_value("UBR"),
            "version": platform.version(),
        }

    return run_tool("get_windows_version", _impl)


def get_boot_time() -> ToolResult:
    """When the PC last started and how long it has been running."""

    def _impl() -> dict:
        boot_ts = psutil.boot_time()
        uptime = max(0.0, datetime.now(timezone.utc).timestamp() - boot_ts)
        return {
            "boot_time": datetime.fromtimestamp(boot_ts, tz=timezone.utc).isoformat(),
            "uptime_seconds": round(uptime, 1),
            "uptime_hours": round(uptime / 3600, 2),
            "uptime_days": round(uptime / 86400, 2),
        }

    return run_tool("get_boot_time", _impl)
