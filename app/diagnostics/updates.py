"""Windows Update diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool, unsupported_result


def get_recent_updates() -> ToolResult:
    """List recently installed Windows updates (hotfixes)."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_recent_updates", "Windows Update history requires Windows"
        )

    def _impl() -> dict:
        from app.core.platform_utils import run_powershell

        out = run_powershell(
            "Get-HotFix | Sort-Object InstalledOn -Descending | "
            "Select-Object HotFixID,Description,InstalledOn -First 15 | "
            "ConvertTo-Json -Compress"
        )
        return {"raw": out.strip()}

    return run_tool("get_recent_updates", _impl)
