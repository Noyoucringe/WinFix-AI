"""Driver diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS, run_powershell_json
from app.core.result import ToolResult, run_tool, unsupported_result


def get_driver_information() -> ToolResult:
    """Installed device drivers: count, unsigned drivers and the oldest ones."""
    if not IS_WINDOWS:
        return unsupported_result("get_driver_information",
                                  "Driver enumeration requires Windows")

    def _impl() -> dict:
        rows = run_powershell_json(
            "Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue |"
            " Where-Object { $_.DeviceName } | Select-Object DeviceName,DeviceClass,"
            "DriverVersion,@{n='Date';e={if($_.DriverDate){$_.DriverDate.ToString('yyyy-MM-dd')}}},"
            "IsSigned | ConvertTo-Json -Compress",
            timeout=45,
        )
        drivers = [{"device": r.get("DeviceName"), "class": r.get("DeviceClass"),
                    "version": r.get("DriverVersion"), "date": r.get("Date"),
                    "signed": r.get("IsSigned")} for r in rows]
        unsigned = [d for d in drivers if d["signed"] is False]
        dated = sorted((d for d in drivers if d["date"]), key=lambda d: d["date"])
        return {"count": len(drivers), "unsigned_count": len(unsigned),
                "unsigned": unsigned[:10], "oldest": dated[:5]}

    return run_tool("get_driver_information", _impl)
