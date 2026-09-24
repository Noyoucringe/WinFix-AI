"""User-facing descriptions of each diagnostic check.

Maps registered diagnostic tool names to the label, icon and data source the
progress screen shows, and turns a finished result into a one-line summary
("Current utilization: 12%"). Presentation only — no logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CheckInfo:
    label: str
    running: str
    icon: str
    source: str


CHECKS: dict[str, CheckInfo] = {
    "get_system_info": CheckInfo("System information", "Reading system details",
                                 "pc", "Win32 API"),
    "get_windows_version": CheckInfo("Windows version", "Reading Windows edition and build",
                                     "pc", "Registry (read-only)"),
    "get_boot_time": CheckInfo("Uptime", "Checking when the PC last started",
                               "clock", "Win32 API"),
    "get_cpu_usage": CheckInfo("CPU usage", "Measuring processor load", "cpu",
                               "Performance counters"),
    "get_memory_usage": CheckInfo("Memory usage", "Measuring memory in use", "memory",
                                  "Performance counters"),
    "get_memory_details": CheckInfo("Memory details", "Reading committed and cached memory",
                                    "memory", "Performance counters"),
    "get_disk_activity": CheckInfo("Disk activity", "Measuring disk reads and writes",
                                   "disk", "Performance counters"),
    "get_disk_usage": CheckInfo("Disk usage", "Measuring free space", "disk",
                                "File system"),
    "get_disk_free_space": CheckInfo("Free space", "Measuring free space on the system drive",
                                     "disk", "File system"),
    "get_disk_partitions": CheckInfo("Drives", "Listing drives", "disk", "File system"),
    "get_reclaimable_space": CheckInfo("Reclaimable space",
                                       "Measuring temporary files and the Recycle Bin",
                                       "delete", "File system, Shell API"),
    "get_running_processes": CheckInfo("Running processes",
                                       "Inspecting resource-intensive applications",
                                       "list", "Process list"),
    "get_top_cpu_processes": CheckInfo("Top CPU apps", "Finding apps using the most CPU",
                                       "list", "Process list"),
    "get_top_memory_processes": CheckInfo("Top memory apps",
                                          "Finding apps using the most memory",
                                          "list", "Process list"),
    "get_unresponsive_apps": CheckInfo("Unresponsive apps",
                                       "Looking for apps that aren't responding",
                                       "app", "Window manager"),
    "get_startup_apps": CheckInfo("Startup applications", "Apps that start with Windows",
                                  "rocket", "WMI"),
    "get_important_services": CheckInfo("Windows services", "Service health", "services",
                                        "Service Control Manager"),
    "get_windows_update_status": CheckInfo("Windows Update service",
                                           "Checking Windows Update and BITS",
                                           "update", "Service Control Manager"),
    "get_network_services_status": CheckInfo("Network services",
                                             "Checking DNS, DHCP and WLAN services",
                                             "services", "Service Control Manager"),
    "get_search_indexer_status": CheckInfo("Windows Search",
                                           "Checking the Windows Search indexer",
                                           "search", "Service Control Manager"),
    "get_recent_updates": CheckInfo("Update history", "Reading recently installed updates",
                                    "update", "WMI"),
    "get_pending_reboot": CheckInfo("Pending restart", "Checking whether a restart is pending",
                                    "restart", "Registry (read-only)"),
    "get_network_adapters": CheckInfo("Network adapters", "Checking network adapters",
                                      "wifi", "IP Helper API"),
    "get_ip_configuration": CheckInfo("IP configuration", "Reading network addresses",
                                      "wifi", "IP Helper API"),
    "ping_gateway": CheckInfo("Router connection", "Checking your router responds",
                              "router", "ICMP echo (ping)"),
    "test_dns": CheckInfo("DNS", "Checking website names resolve", "globe", "DNS resolver"),
    "test_internet": CheckInfo("Internet connection", "Checking the internet is reachable",
                               "globe", "TCP connection test"),
    "get_network_profile": CheckInfo("Network profile", "Reading connection status",
                                     "wifi", "Network List Manager"),
    "get_problem_devices": CheckInfo("Devices", "Checking devices for errors", "device",
                                     "Plug and Play manager"),
    "get_bluetooth_devices": CheckInfo("Bluetooth devices", "Checking Bluetooth hardware",
                                       "bluetooth", "Plug and Play manager"),
    "get_driver_information": CheckInfo("Drivers", "Reading installed drivers", "device",
                                        "WMI"),
    "get_recent_system_errors": CheckInfo("System errors", "Recent event log entries",
                                          "event", "Windows Event Log"),
    "get_recent_application_errors": CheckInfo("Application errors",
                                               "Recent application event log entries",
                                               "event", "Windows Event Log"),
    "get_recent_application_crashes": CheckInfo("App crashes",
                                                "Looking for recent app crashes",
                                                "event", "Windows Error Reporting"),
}


def info(tool: str) -> CheckInfo:
    return CHECKS.get(tool) or CheckInfo(
        tool.replace("get_", "").replace("_", " ").capitalize(), "Running check",
        "info", "Registered diagnostic")


def _gb(value: Any) -> str:
    return f"{value:.1f} GB" if isinstance(value, (int, float)) else "—"


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


_SUMMARIES: dict[str, Callable[[dict], str]] = {
    "get_cpu_usage": lambda d: f"Current utilization: {d['usage_percent']:.0f}%",
    "get_memory_usage": lambda d: (f"Current utilization: {d['usage_percent']:.0f}% · "
                                   f"{_gb(d['used_gb'])} of {_gb(d['total_gb'])}"),
    "get_disk_usage": lambda d: (f"{d['usage_percent']:.1f}% used · "
                                 f"{_gb(d['free_gb'])} free"),
    "get_disk_free_space": lambda d: f"{_gb(d['free_gb'])} free on {d['drive']}",
    "get_running_processes": lambda d: (f"{d['process_count']} processes · "
                                        f"{_count(d['not_responding_count'], 'app')}"
                                        " not responding"),
    "get_startup_apps": lambda d: _count(d["count"], "app") + " start with Windows",
    "get_important_services": lambda d: ("All monitored services are healthy"
                                         if d["healthy"] else
                                         _count(len(d["unhealthy"]), "service")
                                         + " need attention"),
    "get_recent_system_errors": lambda d: (_count(d["count"], "error")
                                           + " in the last 24 hours"),
    "get_recent_application_errors": lambda d: (_count(d["count"], "error")
                                                + " in the last 24 hours"),
    "get_search_indexer_status": lambda d: (f"{d['service']['status_text']} · "
                                            f"indexer using {d['memory_mb']:.0f} MB"),
    "ping_gateway": lambda d: ("Router responds" if d.get("reachable")
                               else "Router not reachable"),
    "test_dns": lambda d: ("Website names resolve" if d["dns_working"]
                           else "Website names don't resolve"),
    "test_internet": lambda d: ("Internet reachable" if d["internet_reachable"]
                                else "Internet not reachable"),
    "get_network_adapters": lambda d: (f"{d['up_count']} of {d['physical_count']} "
                                       "adapters connected"),
    "get_windows_update_status": lambda d: ("Update services healthy" if d["healthy"]
                                            else "Update services need attention"),
    "get_pending_reboot": lambda d: ("Restart pending" if d["reboot_pending"]
                                     else "No restart pending"),
    "get_reclaimable_space": lambda d: f"{d['temp_mb']:.0f} MB of temporary files",
    "get_problem_devices": lambda d: (_count(d["count"], "device") + " reporting errors"),
    "get_bluetooth_devices": lambda d: (_count(d["count"], "Bluetooth device")
                                        + f" · {d['problem_count']} with problems"),
    "get_recent_application_crashes": lambda d: (_count(d["count"], "crash")
                                                 + " in the last 7 days"),
    "get_boot_time": lambda d: f"Running for {d['uptime_days']:.1f} days",
}


def summarize(tool: str, result: dict) -> str:
    """One-line, plain-language summary of a finished check."""
    if not result.get("success"):
        error = result.get("error") or {}
        if error.get("type") == "UnsupportedPlatform":
            return "Not available on this system"
        if error.get("type") == "TimeoutError":
            return "Took too long and was skipped"
        message = str(error.get("message") or "")
        if "denied" in message.lower():
            return "Couldn't read this information. Access was denied."
        return "Couldn't complete this check"
    fn = _SUMMARIES.get(tool)
    if fn:
        try:
            return fn(result.get("data") or {})
        except (KeyError, TypeError, ValueError):
            pass
    return "Completed"
