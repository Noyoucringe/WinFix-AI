"""Windows service diagnostics (read-only).

On non-Windows hosts these degrade gracefully. On Windows they use psutil's
``win_service_*`` API (no shelling out required).
"""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool, unsupported_result

# Services WinFix cares about, grouped by concern.
IMPORTANT_SERVICES = {
    "wuauserv": "Windows Update",
    "bits": "Background Intelligent Transfer",
    "Dnscache": "DNS Client",
    "Dhcp": "DHCP Client",
    "WSearch": "Windows Search",
    "Spooler": "Print Spooler",
    "Audiosrv": "Windows Audio",
    "bthserv": "Bluetooth Support",
    "WlanSvc": "WLAN AutoConfig",
    "nsi": "Network Store Interface",
}

NETWORK_SERVICES = {"Dnscache", "Dhcp", "WlanSvc", "nsi", "bits"}
UPDATE_SERVICES = {"wuauserv", "bits"}


def _service_status(names: dict[str, str]) -> dict:
    import psutil

    services = {}
    for name, label in names.items():
        try:
            svc = psutil.win_service_get(name)
            info = svc.as_dict()
            services[name] = {
                "label": label,
                "status": info.get("status"),
                "start_type": info.get("start_type"),
                "running": info.get("status") == "running",
            }
        except Exception as exc:  # noqa: BLE001 - service may not exist
            services[name] = {"label": label, "status": "unknown", "error": str(exc)}
    return services


def get_important_services() -> ToolResult:
    """Status of the services WinFix monitors."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_important_services", "Windows services require Windows"
        )
    return run_tool(
        "get_important_services",
        lambda: {"services": _service_status(IMPORTANT_SERVICES)},
    )


def get_windows_update_status() -> ToolResult:
    """Status of the Windows Update-related services."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_windows_update_status", "Windows Update requires Windows"
        )

    def _impl() -> dict:
        names = {k: IMPORTANT_SERVICES[k] for k in UPDATE_SERVICES}
        services = _service_status(names)
        healthy = all(s.get("running") for s in services.values())
        return {"healthy": healthy, "services": services}

    return run_tool("get_windows_update_status", _impl)


def get_network_services_status() -> ToolResult:
    """Status of network-related services (DNS, DHCP, WLAN)."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_network_services_status", "Windows services require Windows"
        )

    def _impl() -> dict:
        names = {k: IMPORTANT_SERVICES[k] for k in NETWORK_SERVICES}
        services = _service_status(names)
        healthy = all(
            s.get("running") for k, s in services.items() if k in ("Dnscache", "Dhcp")
        )
        return {"healthy": healthy, "services": services}

    return run_tool("get_network_services_status", _impl)
