"""Populate the tool registry with every diagnostic and remediation tool.

This is the single source of truth for which tools exist, whether they are
read-only, their risk level, timeout and whether they need administrator
rights. The agent, safety layer, API and GUI all derive their behaviour from
what is registered here.
"""

from __future__ import annotations

from app.core.models import RiskLevel
from app.core.tool_registry import ToolParameter, ToolRegistry, ToolSpec
from app.diagnostics import applications as d_app
from app.diagnostics import devices as d_dev
from app.diagnostics import drivers as d_drv
from app.diagnostics import events as d_evt
from app.diagnostics import graphics as d_gfx
from app.diagnostics import network as d_net
from app.diagnostics import performance as d_perf
from app.diagnostics import services as d_svc
from app.diagnostics import startup as d_start
from app.diagnostics import storage as d_stor
from app.diagnostics import system as d_sys
from app.diagnostics import updates as d_upd
from app.remediation import applications as r_app
from app.remediation import network as r_net
from app.remediation import services as r_svc
from app.remediation import storage as r_stor
from app.remediation import system as r_sys

_LIMIT = (ToolParameter("limit", "integer", "How many entries to return", False),)


def _diag(name, fn, category, description, timeout=20.0, **kw) -> ToolSpec:
    return ToolSpec(name=name, function=fn, category=category, description=description,
                    read_only=True, risk_level=RiskLevel.NONE, timeout=timeout, **kw)


def register_diagnostics(reg: ToolRegistry) -> None:
    specs = [
        # system
        _diag("get_system_info", d_sys.get_system_info, "system",
              "Operating system, CPU cores and boot time"),
        _diag("get_windows_version", d_sys.get_windows_version, "system",
              "Windows edition, version and build"),
        _diag("get_boot_time", d_sys.get_boot_time, "system",
              "When the PC last started and how long it has been running"),
        # performance
        _diag("get_cpu_usage", d_perf.get_cpu_usage, "performance",
              "CPU utilization sampled over one second, and CPU speed", timeout=8),
        _diag("get_memory_usage", d_perf.get_memory_usage, "performance",
              "Physical memory and page-file usage", timeout=8),
        _diag("get_memory_details", d_perf.get_memory_details, "performance",
              "Committed, cached and compressed memory", timeout=10),
        _diag("get_disk_activity", d_perf.get_disk_activity, "performance",
              "Disk read/write speed and active time", timeout=8),
        _diag("get_running_processes", d_perf.get_running_processes, "performance",
              "Running apps with memory, CPU and 'Not responding' state", timeout=30),
        _diag("get_top_cpu_processes", d_perf.get_top_cpu_processes, "performance",
              "Apps using the most CPU", timeout=30, parameters=_LIMIT),
        _diag("get_top_memory_processes", d_perf.get_top_memory_processes, "performance",
              "Apps using the most memory", timeout=30, parameters=_LIMIT),
        _diag("get_unresponsive_apps", d_perf.get_unresponsive_apps, "performance",
              "Apps whose windows Windows reports as 'Not responding'", timeout=10),
        _diag("get_startup_apps", d_start.get_startup_apps, "startup",
              "Apps that start automatically when you sign in", timeout=35),
        # network
        _diag("get_network_adapters", d_net.get_network_adapters, "network",
              "Network adapters, link state and addresses"),
        _diag("get_ip_configuration", d_net.get_ip_configuration, "network",
              "IP addresses assigned to each adapter"),
        _diag("ping_gateway", d_net.ping_gateway, "network",
              "Whether the router (default gateway) responds", timeout=30),
        _diag("test_dns", d_net.test_dns, "network",
              "Whether website names can be resolved", timeout=25),
        _diag("test_internet", d_net.test_internet, "network",
              "Whether the internet is reachable", timeout=12),
        _diag("get_network_profile", d_net.get_network_profile, "network",
              "Network category and connectivity reported by Windows", timeout=25),
        # services
        _diag("get_important_services", d_svc.get_important_services, "services",
              "Status of key Windows services"),
        _diag("get_windows_update_status", d_svc.get_windows_update_status, "services",
              "Health of the Windows Update and BITS services"),
        _diag("get_network_services_status", d_svc.get_network_services_status,
              "services", "Health of the DNS, DHCP and WLAN services"),
        _diag("get_search_indexer_status", d_svc.get_search_indexer_status, "services",
              "Windows Search service state and indexer memory use", timeout=15),
        # updates
        _diag("get_recent_updates", d_upd.get_recent_updates, "updates",
              "Recently installed Windows updates", timeout=35),
        _diag("get_pending_reboot", d_upd.get_pending_reboot, "updates",
              "Whether Windows is waiting for a restart to finish updating", timeout=5),
        # devices / drivers
        _diag("get_problem_devices", d_dev.get_problem_devices, "devices",
              "Devices Device Manager reports with an error", timeout=35),
        _diag("get_bluetooth_devices", d_dev.get_bluetooth_devices, "devices",
              "Bluetooth radios and devices and their status", timeout=35),
        _diag("get_driver_information", d_drv.get_driver_information, "drivers",
              "Installed drivers, unsigned and oldest drivers", timeout=50),
        # graphics
        _diag("get_gpu_info", d_gfx.get_gpu_info, "graphics",
              "Graphics adapters, driver version and age, and device status", timeout=30),
        _diag("get_gpu_usage", d_gfx.get_gpu_usage, "graphics",
              "How busy the GPU is and which apps are using it", timeout=40),
        _diag("get_display_driver_errors", d_gfx.get_display_driver_errors, "graphics",
              "Display driver crashes and recoveries in the last 7 days", timeout=35),
        # events
        _diag("get_recent_system_errors", d_evt.get_recent_system_errors, "events",
              "Critical and error events in the System log (24 hours)", timeout=35),
        _diag("get_recent_application_errors", d_evt.get_recent_application_errors,
              "events", "Critical and error events in the Application log (24 hours)",
              timeout=35),
        _diag("get_recent_application_crashes", d_app.get_recent_application_crashes,
              "applications", "App crashes recorded in the last 7 days", timeout=35),
        # storage
        _diag("get_disk_usage", d_stor.get_disk_usage, "storage",
              "Used and free space on the system drive"),
        _diag("get_disk_partitions", d_stor.get_disk_partitions, "storage",
              "All drives and their free space"),
        _diag("get_disk_free_space", d_stor.get_disk_free_space, "storage",
              "Free space on the system drive, with a low-space flag"),
        _diag("get_reclaimable_space", d_stor.get_reclaimable_space, "storage",
              "Space held by temporary files and the Recycle Bin", timeout=20),
    ]
    for spec in specs:
        reg.register(spec)


def _fix(name, fn, category, description, risk, *, admin=False, timeout=120.0,
         parameters=()) -> ToolSpec:
    return ToolSpec(name=name, function=fn, category=category, description=description,
                    read_only=False, risk_level=risk, requires_admin=admin,
                    timeout=timeout, parameters=parameters)


def register_remediations(reg: ToolRegistry) -> None:
    specs = [
        # network
        _fix("flush_dns", r_net.flush_dns, "network",
             "Flush the DNS resolver cache", RiskLevel.LOW),
        _fix("renew_ip_configuration", r_net.renew_ip_configuration, "network",
             "Renew the network address (DHCP lease)", RiskLevel.LOW),
        _fix("release_ip_configuration", r_net.release_ip_configuration, "network",
             "Release the network address (DHCP lease)", RiskLevel.MEDIUM),
        _fix("restart_network_adapter", r_net.restart_network_adapter, "network",
             "Disable and re-enable a network adapter", RiskLevel.MEDIUM, admin=True,
             parameters=(ToolParameter("adapter_name", "string",
                                       "Name of an existing network adapter", True),)),
        _fix("reset_winsock", r_net.reset_winsock, "network",
             "Reset the Winsock catalog (restart required)", RiskLevel.HIGH, admin=True),
        _fix("restart_wlan_service", r_svc.restart_wlan_service, "network",
             "Restart the WLAN AutoConfig service", RiskLevel.LOW, admin=True),
        # services
        _fix("restart_windows_update_service", r_svc.restart_windows_update_service,
             "services", "Restart the Windows Update service", RiskLevel.LOW, admin=True),
        _fix("restart_bits_service", r_svc.restart_bits_service, "services",
             "Restart the Background Intelligent Transfer Service", RiskLevel.LOW,
             admin=True),
        _fix("restart_print_spooler", r_svc.restart_print_spooler, "services",
             "Restart the Print Spooler service", RiskLevel.LOW, admin=True),
        _fix("restart_windows_search", r_svc.restart_windows_search, "services",
             "Restart the Windows Search service", RiskLevel.LOW, admin=True),
        _fix("restart_bluetooth_service", r_svc.restart_bluetooth_service, "services",
             "Restart the Bluetooth Support Service", RiskLevel.LOW, admin=True),
        # storage
        _fix("clear_safe_temp_files", r_stor.clear_safe_temp_files, "storage",
             "Delete temporary files older than a day", RiskLevel.LOW, timeout=300),
        _fix("clear_windows_update_cache_if_safe",
             r_stor.clear_windows_update_cache_if_safe, "storage",
             "Clear the Windows Update download cache", RiskLevel.MEDIUM, admin=True,
             timeout=300),
        _fix("empty_recycle_bin", r_stor.empty_recycle_bin, "storage",
             "Permanently delete the items in the Recycle Bin", RiskLevel.MEDIUM,
             timeout=300),
        # system
        _fix("restart_explorer", r_sys.restart_explorer, "system",
             "Restart Windows Explorer", RiskLevel.LOW),
        _fix("restart_audio_service", r_sys.restart_audio_service, "system",
             "Restart the Windows Audio service", RiskLevel.LOW, admin=True),
        # applications — registered and approval-gated, but no category ever
        # proposes it: WinFix doesn't close your apps on its own initiative.
        _fix("terminate_unresponsive_application",
             r_app.terminate_unresponsive_application, "applications",
             "End one specific app that is not responding", RiskLevel.MEDIUM,
             parameters=(ToolParameter("pid", "integer", "Process ID to end", True),)),
    ]
    for spec in specs:
        reg.register(spec)


def register_all(reg: ToolRegistry) -> None:
    register_diagnostics(reg)
    register_remediations(reg)
