"""System information diagnostics (read-only)."""

from __future__ import annotations

import platform
import socket
from datetime import datetime, timezone

import psutil

from app.core.result import ToolResult, run_tool


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
        }

    return run_tool("get_system_info", _impl)


def get_windows_version() -> ToolResult:
    """Return OS edition/version details."""

    def _impl() -> dict:
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "edition": platform.win32_edition() if hasattr(platform, "win32_edition") else None,
            "is_windows": platform.system() == "Windows",
        }

    return run_tool("get_windows_version", _impl)


def get_boot_time() -> ToolResult:
    """Return system boot time and uptime."""

    def _impl() -> dict:
        boot_ts = psutil.boot_time()
        boot_dt = datetime.fromtimestamp(boot_ts, tz=timezone.utc)
        uptime_seconds = max(0.0, datetime.now(timezone.utc).timestamp() - boot_ts)
        return {
            "boot_time": boot_dt.isoformat(),
            "uptime_seconds": round(uptime_seconds, 1),
            "uptime_hours": round(uptime_seconds / 3600, 2),
        }

    return run_tool("get_boot_time", _impl)
