"""Startup application diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool, unsupported_result


def get_startup_apps() -> ToolResult:
    """Enumerate applications configured to run at startup (Windows only)."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_startup_apps", "Startup app enumeration requires Windows"
        )

    def _impl() -> dict:
        from app.core.platform_utils import run_powershell

        out = run_powershell(
            "Get-CimInstance Win32_StartupCommand | "
            "Select-Object Name,Command,Location,User | "
            "ConvertTo-Json -Compress"
        )
        return {"raw": out.strip()}

    return run_tool("get_startup_apps", _impl)
