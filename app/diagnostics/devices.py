"""Device diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool, unsupported_result


def get_problem_devices() -> ToolResult:
    """List devices reporting an error state (Windows Device Manager)."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_problem_devices", "Device Manager status requires Windows"
        )

    def _impl() -> dict:
        from app.core.platform_utils import run_powershell

        out = run_powershell(
            "Get-PnpDevice | Where-Object { $_.Status -ne 'OK' } | "
            "Select-Object FriendlyName,Class,Status,ProblemDescription | "
            "ConvertTo-Json -Compress"
        )
        return {"raw": out.strip()}

    return run_tool("get_problem_devices", _impl)
