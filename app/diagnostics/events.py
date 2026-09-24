"""Event log diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool, unsupported_result


def _recent_events(log_name: str, tool: str) -> ToolResult:
    if not IS_WINDOWS:
        return unsupported_result(tool, "Windows Event Log requires Windows")

    def _impl() -> dict:
        from app.core.platform_utils import run_powershell

        out = run_powershell(
            f"Get-WinEvent -FilterHashtable @{{LogName='{log_name}';Level=1,2}} "
            "-MaxEvents 20 -ErrorAction SilentlyContinue | "
            "Select-Object TimeCreated,Id,LevelDisplayName,ProviderName,Message | "
            "ConvertTo-Json -Compress"
        )
        return {"log": log_name, "raw": out.strip()}

    return run_tool(tool, _impl)


def get_recent_system_errors() -> ToolResult:
    """Recent System event-log errors and warnings."""
    return _recent_events("System", "get_recent_system_errors")


def get_recent_application_errors() -> ToolResult:
    """Recent Application event-log errors and warnings."""
    return _recent_events("Application", "get_recent_application_errors")
