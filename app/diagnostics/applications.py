"""Application crash diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool, unsupported_result


def get_recent_application_crashes() -> ToolResult:
    """Recent application crash events (Windows Error Reporting)."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_recent_application_crashes", "Crash logs require Windows"
        )

    def _impl() -> dict:
        from app.core.platform_utils import run_powershell

        out = run_powershell(
            "Get-WinEvent -FilterHashtable "
            "@{LogName='Application';ProviderName='Application Error'} "
            "-MaxEvents 15 -ErrorAction SilentlyContinue | "
            "Select-Object TimeCreated,Id,Message | ConvertTo-Json -Compress"
        )
        return {"raw": out.strip()}

    return run_tool("get_recent_application_crashes", _impl)
