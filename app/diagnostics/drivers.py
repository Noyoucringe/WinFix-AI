"""Driver diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool, unsupported_result


def get_driver_information() -> ToolResult:
    """Summarize installed signed drivers (Windows only)."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_driver_information", "Driver enumeration requires Windows"
        )

    def _impl() -> dict:
        from app.core.platform_utils import run_powershell

        out = run_powershell(
            "Get-CimInstance Win32_PnPSignedDriver | "
            "Select-Object DeviceName,DriverVersion,DriverDate,IsSigned -First 100 | "
            "ConvertTo-Json -Compress"
        )
        return {"raw": out.strip()}

    return run_tool("get_driver_information", _impl)
