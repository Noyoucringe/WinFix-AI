"""Populate the tool registry with all diagnostic and remediation tools.

This is the single source of truth for which tools exist, their categories,
risk levels, and whether they are read-only. The agent, safety layer, API, and
GUI all derive their behaviour from what is registered here.
"""

from __future__ import annotations

from app.core.models import RiskLevel
from app.core.tool_registry import ToolParameter, ToolRegistry, ToolSpec

# Diagnostics
from app.diagnostics import applications as d_app
from app.diagnostics import devices as d_dev
from app.diagnostics import drivers as d_drv
from app.diagnostics import events as d_evt
from app.diagnostics import network as d_net
from app.diagnostics import performance as d_perf
from app.diagnostics import services as d_svc
from app.diagnostics import startup as d_start
from app.diagnostics import storage as d_stor
from app.diagnostics import system as d_sys
from app.diagnostics import updates as d_upd

# Remediations
from app.remediation import applications as r_app
from app.remediation import network as r_net
from app.remediation import services as r_svc
from app.remediation import storage as r_stor
from app.remediation import system as r_sys


def _diagnostic(name, fn, category, description, **kw) -> ToolSpec:
    return ToolSpec(
        name=name,
        function=fn,
        category=category,
        description=description,
        read_only=True,
        risk_level=RiskLevel.NONE,
        **kw,
    )


def register_diagnostics(reg: ToolRegistry) -> None:
    specs = [
        # system
        _diagnostic("get_system_info", d_sys.get_system_info, "system",
                    "Basic OS, CPU count, hostname, boot time"),
        _diagnostic("get_windows_version", d_sys.get_windows_version, "system",
                    "Windows edition and version details"),
        _diagnostic("get_boot_time", d_sys.get_boot_time, "system",
                    "System boot time and uptime"),
        # performance
        _diagnostic("get_cpu_usage", d_perf.get_cpu_usage, "performance",
                    "Current CPU utilization percentage", timeout=5),
        _diagnostic("get_memory_usage", d_perf.get_memory_usage, "performance",
                    "Current memory and swap usage"),
        _diagnostic("get_running_processes", d_perf.get_running_processes, "performance",
                    "Count and summary of running processes"),
        _diagnostic("get_top_cpu_processes", d_perf.get_top_cpu_processes, "performance",
                    "Top processes by CPU usage",
                    parameters=(ToolParameter("limit", "integer",
                                              "How many processes", False),)),
        _diagnostic("get_top_memory_processes", d_perf.get_top_memory_processes,
                    "performance", "Top processes by memory usage",
                    parameters=(ToolParameter("limit", "integer",
                                              "How many processes", False),)),
        # startup
        _diagnostic("get_startup_apps", d_start.get_startup_apps, "startup",
                    "Applications configured to run at startup"),
        # network
        _diagnostic("get_network_adapters", d_net.get_network_adapters, "network",
                    "Network interfaces and up/down status"),
        _diagnostic("get_ip_configuration", d_net.get_ip_configuration, "network",
                    "IPv4/IPv6 addresses per interface"),
        _diagnostic("ping_gateway", d_net.ping_gateway, "network",
                    "Ping the default gateway", timeout=20),
        _diagnostic("test_dns", d_net.test_dns, "network",
                    "Resolve well-known hostnames to test DNS", timeout=20),
        _diagnostic("test_internet", d_net.test_internet, "network",
                    "Test outbound internet reachability", timeout=10),
        _diagnostic("get_network_profile", d_net.get_network_profile, "network",
                    "Active network connection profile"),
        # services
        _diagnostic("get_important_services", d_svc.get_important_services, "services",
                    "Status of key Windows services"),
        _diagnostic("get_windows_update_status", d_svc.get_windows_update_status,
                    "services", "Windows Update service health"),
        _diagnostic("get_network_services_status", d_svc.get_network_services_status,
                    "services", "Network service health (DNS, DHCP, WLAN)"),
        # devices / drivers
        _diagnostic("get_problem_devices", d_dev.get_problem_devices, "devices",
                    "Devices reporting an error state"),
        _diagnostic("get_driver_information", d_drv.get_driver_information, "drivers",
                    "Installed signed driver summary"),
        # events
        _diagnostic("get_recent_system_errors", d_evt.get_recent_system_errors,
                    "events", "Recent System event-log errors"),
        _diagnostic("get_recent_application_errors", d_evt.get_recent_application_errors,
                    "events", "Recent Application event-log errors"),
        # storage
        _diagnostic("get_disk_usage", d_stor.get_disk_usage, "storage",
                    "Disk usage for the system drive"),
        _diagnostic("get_disk_partitions", d_stor.get_disk_partitions, "storage",
                    "All partitions and their usage"),
        _diagnostic("get_disk_free_space", d_stor.get_disk_free_space, "storage",
                    "Free space on the system drive"),
        # updates
        _diagnostic("get_recent_updates", d_upd.get_recent_updates, "updates",
                    "Recently installed Windows updates"),
        # applications
        _diagnostic("get_recent_application_crashes",
                    d_app.get_recent_application_crashes, "applications",
                    "Recent application crash events"),
    ]
    for spec in specs:
        reg.register(spec)


def _remediation(name, fn, category, description, risk, **kw) -> ToolSpec:
    return ToolSpec(
        name=name,
        function=fn,
        category=category,
        description=description,
        read_only=False,
        risk_level=risk,
        timeout=kw.pop("timeout", 60),
        **kw,
    )


def register_remediations(reg: ToolRegistry) -> None:
    specs = [
        # network
        _remediation("flush_dns", r_net.flush_dns, "network",
                     "Flush the DNS resolver cache", RiskLevel.LOW),
        _remediation("renew_ip_configuration", r_net.renew_ip_configuration, "network",
                     "Renew the DHCP lease", RiskLevel.LOW),
        _remediation("release_ip_configuration", r_net.release_ip_configuration,
                     "network", "Release the DHCP lease", RiskLevel.MEDIUM),
        _remediation("restart_network_adapter", r_net.restart_network_adapter,
                     "network", "Disable and re-enable a network adapter",
                     RiskLevel.MEDIUM, requires_admin=True,
                     parameters=(ToolParameter("adapter_name", "string",
                                               "Adapter to restart", True),)),
        _remediation("reset_winsock", r_net.reset_winsock, "network",
                     "Reset the Winsock catalog (reboot recommended)",
                     RiskLevel.HIGH, requires_admin=True),
        # services
        _remediation("restart_windows_update_service",
                     r_svc.restart_windows_update_service, "services",
                     "Restart the Windows Update service", RiskLevel.LOW,
                     requires_admin=True),
        _remediation("restart_print_spooler", r_svc.restart_print_spooler, "services",
                     "Restart the Print Spooler service", RiskLevel.LOW,
                     requires_admin=True),
        _remediation("restart_windows_search", r_svc.restart_windows_search, "services",
                     "Restart the Windows Search service", RiskLevel.LOW,
                     requires_admin=True),
        _remediation("restart_bluetooth_service", r_svc.restart_bluetooth_service,
                     "services", "Restart the Bluetooth Support service", RiskLevel.LOW,
                     requires_admin=True),
        _remediation("restart_bits_service", r_svc.restart_bits_service, "services",
                     "Restart the BITS service", RiskLevel.LOW, requires_admin=True),
        # storage
        _remediation("clear_safe_temp_files", r_stor.clear_safe_temp_files, "storage",
                     "Clear user and system TEMP directories", RiskLevel.LOW),
        _remediation("clear_windows_update_cache_if_safe",
                     r_stor.clear_windows_update_cache_if_safe, "storage",
                     "Clear the Windows Update download cache", RiskLevel.MEDIUM,
                     requires_admin=True),
        _remediation("empty_recycle_bin", r_stor.empty_recycle_bin, "storage",
                     "Empty the Recycle Bin", RiskLevel.MEDIUM),
        # system
        _remediation("restart_explorer", r_sys.restart_explorer, "system",
                     "Restart Windows Explorer (the shell)", RiskLevel.LOW),
        _remediation("restart_audio_service", r_sys.restart_audio_service, "system",
                     "Restart the Windows Audio service", RiskLevel.LOW,
                     requires_admin=True),
        # applications
        _remediation("terminate_unresponsive_application",
                     r_app.terminate_unresponsive_application, "applications",
                     "Terminate a specific unresponsive process by PID",
                     RiskLevel.MEDIUM,
                     parameters=(ToolParameter("pid", "integer",
                                               "Process ID to terminate", True),)),
    ]
    for spec in specs:
        reg.register(spec)


def register_all(reg: ToolRegistry) -> None:
    register_diagnostics(reg)
    register_remediations(reg)
