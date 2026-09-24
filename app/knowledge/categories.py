"""Troubleshooting categories.

Each category maps a class of problem to the diagnostics worth running
(standard and thorough depth), the only fixes that may ever be proposed for it,
and an optional general safe step when no specific fault is measured.
Declarative data: the planner, analyzer and remediation engine all read it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.models import Category


@dataclass(frozen=True)
class CategorySpec:
    category: Category
    title: str
    keywords: tuple[str, ...]
    symptoms: str
    diagnostic_tools: tuple[str, ...]
    thorough_tools: tuple[str, ...] = ()
    remediation_tools: tuple[str, ...] = ()
    general_fix: str | None = None
    verification_tools: tuple[str, ...] = ()
    icon: str = "wrench"


_PERF = ("get_cpu_usage", "get_memory_usage", "get_disk_usage", "get_running_processes",
         "get_startup_apps", "get_important_services", "get_recent_system_errors")
_PERF_DEEP = ("get_memory_details", "get_disk_activity", "get_boot_time",
              "get_search_indexer_status", "get_unresponsive_apps")
_NET = ("get_network_adapters", "ping_gateway", "test_dns", "test_internet",
        "get_network_services_status")

CATEGORIES: dict[Category, CategorySpec] = {
    Category.SLOW_COMPUTER: CategorySpec(
        Category.SLOW_COMPUTER, "Slow computer",
        ("slow", "sluggish", "laggy", "lagging", "freez", "hang", "unresponsive",
         "takes forever", "performance"),
        "The PC feels slow or unresponsive.",
        _PERF, _PERF_DEEP,
        remediation_tools=("restart_windows_search", "clear_safe_temp_files"),
        verification_tools=("get_memory_usage", "get_cpu_usage"), icon="speed"),
    Category.HIGH_CPU: CategorySpec(
        Category.HIGH_CPU, "High CPU usage",
        ("cpu", "processor", "100%", "fan", "hot", "overheat"),
        "CPU usage is unusually high.",
        ("get_cpu_usage", "get_running_processes", "get_top_cpu_processes",
         "get_important_services", "get_recent_system_errors"),
        ("get_search_indexer_status", "get_boot_time"),
        remediation_tools=("restart_windows_search",),
        verification_tools=("get_cpu_usage",), icon="cpu"),
    Category.HIGH_MEMORY: CategorySpec(
        Category.HIGH_MEMORY, "High memory usage",
        ("memory", "ram", "out of memory", "leak"),
        "Memory usage is high.",
        ("get_memory_usage", "get_memory_details", "get_running_processes",
         "get_important_services"),
        ("get_search_indexer_status", "get_unresponsive_apps"),
        remediation_tools=("restart_windows_search",),
        verification_tools=("get_memory_usage",), icon="memory"),
    Category.LOW_DISK_SPACE: CategorySpec(
        Category.LOW_DISK_SPACE, "Storage almost full",
        ("disk", "storage", "full", "space", "no room", "c drive", "c:"),
        "The system drive is running out of space.",
        ("get_disk_free_space", "get_disk_partitions", "get_reclaimable_space"),
        ("get_disk_activity",),
        remediation_tools=("clear_safe_temp_files", "empty_recycle_bin",
                           "clear_windows_update_cache_if_safe"),
        verification_tools=("get_disk_free_space", "get_reclaimable_space"), icon="disk"),
    Category.INTERNET_DOWN: CategorySpec(
        Category.INTERNET_DOWN, "Internet not working",
        ("internet", "offline", "can't connect", "cannot connect", "no connection",
         "network"),
        "The PC can't reach the internet.",
        _NET, ("get_ip_configuration", "get_network_profile"),
        remediation_tools=("restart_network_adapter", "flush_dns",
                           "renew_ip_configuration", "reset_winsock"),
        verification_tools=("ping_gateway", "test_internet"), icon="globe"),
    Category.WIFI_DISCONNECTING: CategorySpec(
        Category.WIFI_DISCONNECTING, "Wi-Fi disconnecting",
        ("wifi", "wi-fi", "wireless", "disconnect", "drops", "keeps dropping"),
        "Wi-Fi connectivity is intermittent.",
        _NET, ("get_network_profile", "get_recent_system_errors"),
        remediation_tools=("restart_wlan_service", "restart_network_adapter",
                           "renew_ip_configuration", "flush_dns"),
        general_fix="renew_ip_configuration",
        verification_tools=("ping_gateway", "test_internet"), icon="wifi"),
    Category.DNS_PROBLEMS: CategorySpec(
        Category.DNS_PROBLEMS, "Websites won't load",
        ("dns", "can't resolve", "cannot resolve", "site won't load", "server not found",
         "website", "webpage", "browser"),
        "Websites fail to load although the network is up.",
        ("test_dns", "test_internet", "ping_gateway", "get_network_services_status"),
        ("get_network_adapters",),
        remediation_tools=("flush_dns", "renew_ip_configuration"),
        general_fix="flush_dns",
        verification_tools=("test_dns",), icon="globe"),
    Category.WINDOWS_UPDATE: CategorySpec(
        Category.WINDOWS_UPDATE, "Windows Update isn't working",
        ("windows update", "update", "updating", "won't update", "update stuck",
         "update error", "update failed"),
        "Windows Update fails or is stuck.",
        ("get_windows_update_status", "get_pending_reboot", "get_disk_free_space",
         "get_recent_updates", "get_recent_system_errors"),
        ("get_reclaimable_space", "test_internet"),
        remediation_tools=("restart_windows_update_service", "restart_bits_service",
                           "clear_safe_temp_files", "clear_windows_update_cache_if_safe"),
        general_fix="restart_windows_update_service",
        verification_tools=("get_windows_update_status",), icon="update"),
    Category.BLUETOOTH: CategorySpec(
        Category.BLUETOOTH, "Bluetooth isn't working",
        ("bluetooth", "headphones", "earbuds", "pairing", "pair", "airpods"),
        "Bluetooth devices don't connect or pair.",
        ("get_bluetooth_devices", "get_important_services", "get_problem_devices"),
        ("get_driver_information",),
        remediation_tools=("restart_bluetooth_service",),
        general_fix="restart_bluetooth_service",
        verification_tools=("get_important_services",), icon="bluetooth"),
    Category.AUDIO: CategorySpec(
        Category.AUDIO, "No sound",
        ("audio", "sound", "speaker", "microphone", "mic", "volume"),
        "Sound output or input isn't working.",
        ("get_important_services", "get_problem_devices"),
        ("get_driver_information",),
        remediation_tools=("restart_audio_service",),
        general_fix="restart_audio_service",
        verification_tools=("get_important_services",), icon="speaker"),
    Category.PRINTER: CategorySpec(
        Category.PRINTER, "Printer isn't working",
        ("printer", "print", "printing", "spooler"),
        "Printing fails or jobs are stuck.",
        ("get_important_services", "get_problem_devices"),
        remediation_tools=("restart_print_spooler",),
        general_fix="restart_print_spooler",
        verification_tools=("get_important_services",), icon="print"),
    Category.APP_CRASHES: CategorySpec(
        Category.APP_CRASHES, "Apps keep crashing",
        ("crash", "crashes", "keeps closing", "not responding", "stopped working"),
        "Apps crash or stop responding.",
        ("get_recent_application_crashes", "get_recent_application_errors",
         "get_memory_usage", "get_running_processes", "get_disk_free_space"),
        ("get_unresponsive_apps",),
        remediation_tools=("clear_safe_temp_files",),
        verification_tools=("get_memory_usage",), icon="app"),
    Category.STARTUP_PROBLEMS: CategorySpec(
        Category.STARTUP_PROBLEMS, "Slow to start",
        ("startup", "boot", "slow to start", "takes long to start", "long time to start",
         "sign in"),
        "The PC takes a long time to start.",
        ("get_startup_apps", "get_boot_time", "get_disk_usage", "get_memory_usage",
         "get_recent_system_errors"),
        ("get_disk_activity", "get_pending_reboot"),
        remediation_tools=("clear_safe_temp_files",),
        verification_tools=("get_boot_time",), icon="power"),
    Category.DEVICE_DRIVER: CategorySpec(
        Category.DEVICE_DRIVER, "Device isn't working",
        ("driver", "device", "not recognized", "device manager", "unknown device",
         "usb", "webcam", "camera", "keyboard", "mouse"),
        "A device or its driver is malfunctioning.",
        ("get_problem_devices", "get_driver_information", "get_recent_system_errors"),
        (),
        verification_tools=("get_problem_devices",), icon="device"),
    Category.WINDOWS_SEARCH: CategorySpec(
        Category.WINDOWS_SEARCH, "Windows Search isn't working",
        ("search", "windows search", "start menu search", "can't find files", "indexing"),
        "Windows Search returns no results.",
        ("get_search_indexer_status", "get_important_services",
         "get_recent_application_errors"),
        ("get_memory_usage",),
        remediation_tools=("restart_windows_search",),
        general_fix="restart_windows_search",
        verification_tools=("get_search_indexer_status",), icon="search"),
}

# Fallback plan when a problem can't be classified: a broad, cheap sweep.
GENERAL_TOOLS = ("get_cpu_usage", "get_memory_usage", "get_disk_usage",
                 "get_running_processes", "get_important_services",
                 "get_recent_system_errors", "test_internet")


def get_category_spec(category: Category) -> CategorySpec | None:
    return CATEGORIES.get(category)


def category_icon(category: Category | str | None) -> str:
    try:
        spec = CATEGORIES.get(Category(category)) if category else None
    except ValueError:
        spec = None
    return spec.icon if spec else "wrench"


def _hits(text: str, keyword: str) -> bool:
    # Short keywords must match whole words ("fan" must not match "infant").
    if len(keyword) <= 4 and keyword.isalpha():
        return re.search(rf"\b{re.escape(keyword)}", text) is not None
    return keyword in text


def classify(problem: str) -> Category:
    """Offline classifier: score categories by keyword hits (phrases weigh more)."""
    text = (problem or "").lower().replace("’", "'")
    best: tuple[int, Category] = (0, Category.UNKNOWN)
    for spec in CATEGORIES.values():
        score = 0
        for kw in spec.keywords:
            if _hits(text, kw):
                score += 2 if " " in kw or "-" in kw else 1
        if score > best[0]:
            best = (score, spec.category)
    return best[1]
