"""Device diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS, run_powershell_json
from app.core.result import ToolResult, run_tool, unsupported_result


def _device(row: dict) -> dict:
    return {
        "name": row.get("FriendlyName") or "Unknown device",
        "class": row.get("Class"),
        "status": row.get("Status"),
        "problem": row.get("Problem"),
        "present": row.get("Present"),
    }


def get_problem_devices() -> ToolResult:
    """Present devices that Device Manager reports with an error."""
    if not IS_WINDOWS:
        return unsupported_result("get_problem_devices",
                                  "Device Manager status requires Windows")

    def _impl() -> dict:
        rows = run_powershell_json(
            "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |"
            " Where-Object { $_.Status -eq 'Error' -or $_.Status -eq 'Degraded' } |"
            " Select-Object FriendlyName,Class,Status,"
            "@{n='Problem';e={[string]$_.Problem}},Present | ConvertTo-Json -Compress",
            timeout=30,
        )
        devices = [_device(r) for r in rows]
        return {"count": len(devices), "devices": devices}

    return run_tool("get_problem_devices", _impl)


def get_bluetooth_devices() -> ToolResult:
    """Bluetooth radios and paired devices, with their Device Manager status."""
    if not IS_WINDOWS:
        return unsupported_result("get_bluetooth_devices",
                                  "Bluetooth inspection requires Windows")

    def _impl() -> dict:
        rows = run_powershell_json(
            "Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction SilentlyContinue |"
            " Select-Object FriendlyName,Class,Status,"
            "@{n='Problem';e={[string]$_.Problem}},Present | ConvertTo-Json -Compress",
            timeout=30,
        )
        devices = [_device(r) for r in rows]
        problems = [d for d in devices if d["status"] not in ("OK", None)]
        return {"count": len(devices), "adapter_present": bool(devices),
                "problem_count": len(problems), "devices": devices}

    return run_tool("get_bluetooth_devices", _impl)
