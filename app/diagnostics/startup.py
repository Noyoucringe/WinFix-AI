"""Startup application diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS, run_powershell_json
from app.core.result import ToolResult, run_tool, unsupported_result


def get_startup_apps() -> ToolResult:
    """Apps configured to start when you sign in (Run keys and Startup folders)."""
    if not IS_WINDOWS:
        return unsupported_result("get_startup_apps",
                                  "Startup app enumeration requires Windows")

    def _impl() -> dict:
        rows = run_powershell_json(
            "Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue |"
            " Select-Object Name,Location | ConvertTo-Json -Compress",
            timeout=30,
        )
        apps = [{"name": r.get("Name"), "location": r.get("Location")}
                for r in rows if r.get("Name")]
        return {"count": len(apps), "apps": apps}

    return run_tool("get_startup_apps", _impl)
