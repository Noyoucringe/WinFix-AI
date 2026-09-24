"""Recorded evidence for deterministic end-to-end tests.

Each scenario maps diagnostic tool names to the ``data`` a real Windows PC
returned for that situation. ``install`` patches the registry so diagnostics
return these values while everything else (safety, analysis, proposals,
verification) runs for real. Remediation tools are never patched here.
"""

from __future__ import annotations

import copy
from typing import Any

from app.core.result import error_result, success_result

_GROUPS_SLOW = [
    {"name": "chrome.exe", "display_name": "Google Chrome", "count": 14,
     "memory_mb": 4915.0, "cpu_percent": 3.1, "not_responding": False, "pids": [10, 11]},
    {"name": "SearchIndexer.exe", "display_name": "Windows Search indexer", "count": 1,
     "memory_mb": 2150.0, "cpu_percent": 0.0, "not_responding": True, "pids": [20]},
    {"name": "ms-teams.exe", "display_name": "Microsoft Teams", "count": 4,
     "memory_mb": 1126.0, "cpu_percent": 0.8, "not_responding": False, "pids": [30]},
]

SLOW_PC: dict[str, dict[str, Any]] = {
    "get_cpu_usage": {"usage_percent": 10.9, "per_cpu_percent": [10.0], "speed_mhz": 2420,
                      "logical_cpus": 8, "physical_cpus": 4, "sample_seconds": 1},
    "get_memory_usage": {"usage_percent": 73.2, "total_gb": 15.7, "available_gb": 4.2,
                         "used_gb": 11.5, "swap_percent": 12.0, "swap_total_gb": 4.0},
    "get_disk_usage": {"drive": "C:", "usage_percent": 82.6, "total_gb": 275.0,
                       "used_gb": 227.3, "free_gb": 47.7},
    "get_running_processes": {"process_count": 214, "app_count": 90,
                              "not_responding_count": 1, "groups": _GROUPS_SLOW,
                              "processes": []},
    "get_startup_apps": {"count": 6, "apps": []},
    "get_important_services": {"services": {
        "WSearch": {"name": "WSearch", "label": "Windows Search", "status": "running",
                    "status_text": "Running", "start_type": "automatic", "running": True,
                    "healthy": True}}, "unhealthy": [], "healthy": True},
    "get_recent_system_errors": {"log": "System", "hours": 24, "count": 2,
                                 "critical_count": 0, "top_sources": [], "events": []},
}

# After "Restart Windows Search": the indexer released its memory but other
# apps used it since, so memory pressure remains (the design's failure case).
SLOW_PC_AFTER_FIX_STILL_HIGH = copy.deepcopy(SLOW_PC)
SLOW_PC_AFTER_FIX_STILL_HIGH["get_running_processes"]["groups"][1].update(
    memory_mb=96.0, not_responding=False)
SLOW_PC_AFTER_FIX_STILL_HIGH["get_running_processes"]["not_responding_count"] = 0
SLOW_PC_AFTER_FIX_STILL_HIGH["get_memory_usage"].update(usage_percent=72.0, used_gb=11.3)

# The design's success case: indexer fixed and memory back to normal.
SLOW_PC_AFTER_FIX_RESOLVED = copy.deepcopy(SLOW_PC_AFTER_FIX_STILL_HIGH)
SLOW_PC_AFTER_FIX_RESOLVED["get_memory_usage"].update(usage_percent=60.5, used_gb=9.5)

HEALTHY_PC: dict[str, dict[str, Any]] = {
    **copy.deepcopy(SLOW_PC),
    "get_memory_usage": {"usage_percent": 41.0, "total_gb": 15.7, "available_gb": 9.3,
                         "used_gb": 6.4, "swap_percent": 2.0, "swap_total_gb": 4.0},
    "get_running_processes": {"process_count": 180, "app_count": 70,
                              "not_responding_count": 0,
                              "groups": [dict(_GROUPS_SLOW[0], memory_mb=900.0)],
                              "processes": []},
}

STORAGE_FULL: dict[str, dict[str, Any]] = {
    "get_disk_free_space": {"drive": "C:", "free_gb": 6.1, "total_gb": 237.0,
                            "usage_percent": 97.4, "free_percent": 2.6, "low_space": True},
    "get_disk_partitions": {"partition_count": 1, "partitions": []},
    "get_reclaimable_space": {"temp_mb": 3840.0, "temp_locations": [],
                              "recycle_bin_mb": 1210.0, "recycle_bin_items": 42},
}
STORAGE_AFTER_CLEANUP = copy.deepcopy(STORAGE_FULL)
STORAGE_AFTER_CLEANUP["get_disk_free_space"].update(free_gb=9.8, usage_percent=95.9,
                                                    low_space=True)
STORAGE_AFTER_CLEANUP["get_reclaimable_space"].update(temp_mb=120.0)

_ADAPTERS = {"adapter_count": 2, "up_count": 1, "physical_count": 1, "adapters": [
    {"name": "Wi-Fi", "is_up": True, "speed_mbps": 866, "mtu": 1500, "wireless": True,
     "virtual": False, "ipv4": ["192.168.1.23"]},
    {"name": "Loopback Pseudo-Interface 1", "is_up": True, "speed_mbps": 0, "mtu": 1500,
     "wireless": False, "virtual": True, "ipv4": ["127.0.0.1"]}]}

WIFI_ROUTER_DOWN: dict[str, dict[str, Any]] = {
    "get_network_adapters": _ADAPTERS,
    "ping_gateway": {"gateway": "192.168.1.1", "interface": "Wi-Fi", "reachable": False,
                     "replies": 0, "sent": 3, "loss_percent": 100},
    "test_dns": {"dns_working": False, "resolved_count": 0, "total": 2, "results": {}},
    "test_internet": {"internet_reachable": False, "target": "1.1.1.1", "error": "timeout"},
    "get_network_services_status": {"services": {
        "WlanSvc": {"name": "WlanSvc", "label": "WLAN AutoConfig", "status": "running",
                    "status_text": "Running", "running": True, "healthy": True}},
        "healthy": True},
}

DNS_BROKEN: dict[str, dict[str, Any]] = {
    "test_dns": {"dns_working": False, "resolved_count": 0, "total": 2, "results": {}},
    "test_internet": {"internet_reachable": True, "target": "1.1.1.1", "error": None},
    "ping_gateway": {"gateway": "192.168.1.1", "interface": "Wi-Fi", "reachable": True,
                     "replies": 3, "sent": 3, "loss_percent": 0},
    "get_network_services_status": {"services": {}, "healthy": True},
}
DNS_FIXED = copy.deepcopy(DNS_BROKEN)
DNS_FIXED["test_dns"].update(dns_working=True, resolved_count=2)

UPDATE_SERVICE_STOPPED: dict[str, dict[str, Any]] = {
    "get_windows_update_status": {"services": {
        "wuauserv": {"name": "wuauserv", "label": "Windows Update", "status": "stopped",
                     "status_text": "Stopped", "start_type": "automatic", "running": False,
                     "healthy": False},
        "bits": {"name": "bits", "label": "Background Intelligent Transfer Service",
                 "status": "running", "status_text": "Running", "start_type": "manual",
                 "running": True, "healthy": True}}, "disabled": [], "healthy": False},
    "get_pending_reboot": {"reboot_pending": False, "reasons": [],
                           "file_operations_pending": False},
    "get_disk_free_space": {"drive": "C:", "free_gb": 60.0, "total_gb": 237.0,
                            "usage_percent": 74.7, "free_percent": 25.3, "low_space": False},
    "get_recent_updates": {"count": 0, "updates": [], "last_installed": None},
    "get_recent_system_errors": {"count": 0, "critical_count": 0, "top_sources": [],
                                 "events": []},
}

BLUETOOTH_MISSING: dict[str, dict[str, Any]] = {
    "get_bluetooth_devices": {"count": 0, "adapter_present": False, "problem_count": 0,
                              "devices": []},
    "get_important_services": {"services": {
        "bthserv": {"name": "bthserv", "label": "Bluetooth Support Service",
                    "status": "stopped", "status_text": "Stopped", "start_type": "manual",
                    "running": False, "healthy": True}}, "unhealthy": [], "healthy": True},
    "get_problem_devices": {"count": 0, "devices": []},
}

SCENARIOS = {
    "slow_pc": SLOW_PC,
    "healthy_pc": HEALTHY_PC,
    "storage_full": STORAGE_FULL,
    "wifi_router_down": WIFI_ROUTER_DOWN,
    "dns_broken": DNS_BROKEN,
    "update_service_stopped": UPDATE_SERVICE_STOPPED,
    "bluetooth_missing": BLUETOOTH_MISSING,
}


def results_for(evidence: dict[str, dict[str, Any]]) -> dict[str, dict]:
    """Wrap raw evidence in the standard result contract."""
    return {tool: success_result(tool, copy.deepcopy(d)) for tool, d in evidence.items()}


class ScenarioRegistry:
    """Swaps diagnostic results for recorded evidence on a live registry."""

    def __init__(self, monkeypatch, registry) -> None:
        self._registry = registry
        self._original = registry.execute_tool
        self._evidence: dict[str, dict] = {}
        self._after: dict[str, dict] | None = None
        self.remediation_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(registry, "execute_tool", self._execute)

    def use(self, evidence: dict[str, dict[str, Any]],
            after_fix: dict[str, dict[str, Any]] | None = None) -> None:
        """Serve ``evidence``; once any fix runs, serve ``after_fix`` instead."""
        self._evidence = copy.deepcopy(evidence)
        self._after = copy.deepcopy(after_fix) if after_fix is not None else None

    def _execute(self, name, arguments=None):
        spec = self._registry.get_tool(name)
        self._registry.validate_arguments(spec, arguments or {})
        if not spec.read_only:
            # Remediations are recorded, never run, in tests.
            self.remediation_calls.append((name, dict(arguments or {})))
            if self._after is not None:
                self._evidence = self._after
            return success_result(name, {"simulated": True})
        if name in self._evidence:
            return success_result(name, copy.deepcopy(self._evidence[name]))
        return error_result(name, "NotCollected", "Not part of this scenario")
