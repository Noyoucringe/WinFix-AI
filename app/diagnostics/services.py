"""Windows service diagnostics (read-only, via psutil's Service Control Manager API)."""

from __future__ import annotations

import psutil

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool, unsupported_result

IMPORTANT_SERVICES = {
    "wuauserv": "Windows Update",
    "bits": "Background Intelligent Transfer Service",
    "Dnscache": "DNS Client",
    "Dhcp": "DHCP Client",
    "WSearch": "Windows Search",
    "Spooler": "Print Spooler",
    "Audiosrv": "Windows Audio",
    "AudioEndpointBuilder": "Windows Audio Endpoint Builder",
    "bthserv": "Bluetooth Support Service",
    "WlanSvc": "WLAN AutoConfig",
    "nsi": "Network Store Interface Service",
}
NETWORK_SERVICES = ("Dnscache", "Dhcp", "WlanSvc", "nsi")
UPDATE_SERVICES = ("wuauserv", "bits")

# Services that are demand-started: "stopped" is normal for them when idle.
_ON_DEMAND = {"wuauserv", "bits", "bthserv"}

_STATUS_TEXT = {
    "running": "Running",
    "stopped": "Stopped",
    "start_pending": "Starting",
    "stop_pending": "Stopping",
    "paused": "Paused",
    "pause_pending": "Pausing",
    "continue_pending": "Resuming",
}


def service_status(name: str) -> dict:
    """Status of one service. Never raises."""
    label = IMPORTANT_SERVICES.get(name, name)
    try:
        info = psutil.win_service_get(name).as_dict()
    except Exception as exc:  # noqa: BLE001 - missing service / access denied
        return {"name": name, "label": label, "status": "not_found",
                "status_text": "Not installed", "running": False,
                "healthy": name in _ON_DEMAND, "error": str(exc)[:200]}
    status = info.get("status") or "unknown"
    start_type = info.get("start_type") or "unknown"
    running = status == "running"
    # A stopped demand-start or disabled service is not a fault by itself.
    healthy = running or (status == "stopped" and
                          (name in _ON_DEMAND or start_type in ("manual", "disabled")))
    return {
        "name": name,
        "label": info.get("display_name") or label,
        "status": status,
        "status_text": _STATUS_TEXT.get(status, status.replace("_", " ").title()),
        "start_type": start_type,
        "running": running,
        "healthy": healthy,
        "pid": info.get("pid"),
    }


def _statuses(names) -> dict[str, dict]:
    return {n: service_status(n) for n in names}


def get_important_services() -> ToolResult:
    """Status of the Windows services WinFix monitors."""
    if not IS_WINDOWS:
        return unsupported_result("get_important_services",
                                  "Windows services require Windows")

    def _impl() -> dict:
        services = _statuses(IMPORTANT_SERVICES)
        unhealthy = [s["name"] for s in services.values() if not s["healthy"]]
        return {"services": services, "unhealthy": unhealthy,
                "healthy": not unhealthy}

    return run_tool("get_important_services", _impl)


def get_windows_update_status() -> ToolResult:
    """Health of the Windows Update and BITS services."""
    if not IS_WINDOWS:
        return unsupported_result("get_windows_update_status",
                                  "Windows Update requires Windows")

    def _impl() -> dict:
        services = _statuses(UPDATE_SERVICES)
        disabled = [n for n, s in services.items() if s.get("start_type") == "disabled"]
        return {"services": services, "disabled": disabled,
                "healthy": all(s["healthy"] for s in services.values()) and not disabled}

    return run_tool("get_windows_update_status", _impl)


def get_network_services_status() -> ToolResult:
    """Health of the DNS Client, DHCP Client and WLAN services."""
    if not IS_WINDOWS:
        return unsupported_result("get_network_services_status",
                                  "Windows services require Windows")

    def _impl() -> dict:
        services = _statuses(NETWORK_SERVICES)
        return {"services": services,
                "healthy": all(services[n]["healthy"] for n in ("Dnscache", "Dhcp"))}

    return run_tool("get_network_services_status", _impl)


def get_search_indexer_status() -> ToolResult:
    """Windows Search service state and the indexer's memory/CPU use."""
    if not IS_WINDOWS:
        return unsupported_result("get_search_indexer_status",
                                  "Windows Search requires Windows")

    def _impl() -> dict:
        service = service_status("WSearch")
        memory_mb = cpu = 0.0
        count = 0
        responding = True
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() != "searchindexer.exe":
                continue
            try:
                memory_mb += proc.memory_info().rss / (1024 ** 2)
                cpu += proc.cpu_percent(interval=0.2) / (psutil.cpu_count() or 1)
                count += 1
                if proc.status() in (psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE):
                    responding = False
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {
            "service": service,
            "process_running": count > 0,
            "memory_mb": round(memory_mb, 1),
            "cpu_percent": round(cpu, 1),
            "responding": responding and (count > 0 or not service["running"]),
        }

    return run_tool("get_search_indexer_status", _impl)
