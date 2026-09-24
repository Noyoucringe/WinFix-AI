"""Troubleshooting category definitions.

Each category maps a class of user problem to:

* keywords used for lightweight, offline classification;
* the diagnostic tools relevant to that problem;
* the remediation actions allowed for that problem;
* the verification tools used to confirm improvement.

This is deliberately declarative data so the planner, agent, and remediation
engine all agree on what is relevant, and so new categories can be added
without touching engine code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models import Category


@dataclass(frozen=True)
class CategorySpec:
    category: Category
    title: str
    keywords: tuple[str, ...]
    symptoms: str
    diagnostic_tools: tuple[str, ...]
    remediation_tools: tuple[str, ...] = field(default_factory=tuple)
    verification_tools: tuple[str, ...] = field(default_factory=tuple)


CATEGORIES: dict[Category, CategorySpec] = {
    Category.SLOW_COMPUTER: CategorySpec(
        category=Category.SLOW_COMPUTER,
        title="Slow computer",
        keywords=("slow", "sluggish", "laggy", "freezing", "hang", "unresponsive",
                  "takes forever", "slow after startup"),
        symptoms="The system feels slow or unresponsive during normal use.",
        diagnostic_tools=("get_cpu_usage", "get_memory_usage", "get_disk_usage",
                          "get_top_cpu_processes", "get_top_memory_processes",
                          "get_startup_apps"),
        remediation_tools=("terminate_unresponsive_application", "clear_safe_temp_files",
                           "restart_explorer"),
        verification_tools=("get_cpu_usage", "get_memory_usage"),
    ),
    Category.HIGH_CPU: CategorySpec(
        category=Category.HIGH_CPU,
        title="High CPU usage",
        keywords=("cpu", "processor", "100%", "fan", "hot", "overheating"),
        symptoms="CPU usage is unusually high.",
        diagnostic_tools=("get_cpu_usage", "get_top_cpu_processes",
                          "get_running_processes"),
        remediation_tools=("terminate_unresponsive_application",),
        verification_tools=("get_cpu_usage",),
    ),
    Category.HIGH_MEMORY: CategorySpec(
        category=Category.HIGH_MEMORY,
        title="High memory usage",
        keywords=("memory", "ram", "out of memory", "leak"),
        symptoms="Memory usage is high and the system may be paging.",
        diagnostic_tools=("get_memory_usage", "get_top_memory_processes",
                          "get_running_processes"),
        remediation_tools=("terminate_unresponsive_application",),
        verification_tools=("get_memory_usage",),
    ),
    Category.LOW_DISK_SPACE: CategorySpec(
        category=Category.LOW_DISK_SPACE,
        title="Low disk space",
        keywords=("disk", "storage", "full", "space", "no room", "c drive"),
        symptoms="The system drive is running out of free space.",
        diagnostic_tools=("get_disk_usage", "get_disk_free_space",
                          "get_disk_partitions"),
        remediation_tools=("clear_safe_temp_files", "clear_windows_update_cache_if_safe",
                           "empty_recycle_bin"),
        verification_tools=("get_disk_free_space",),
    ),
    Category.INTERNET_DOWN: CategorySpec(
        category=Category.INTERNET_DOWN,
        title="Internet not working",
        keywords=("internet", "no internet", "offline", "can't connect",
                  "cannot connect", "no connection"),
        symptoms="The machine cannot reach the internet.",
        diagnostic_tools=("get_network_adapters", "get_ip_configuration",
                          "ping_gateway", "test_dns", "test_internet",
                          "get_network_services_status"),
        remediation_tools=("renew_ip_configuration", "restart_network_adapter",
                           "flush_dns", "reset_winsock"),
        verification_tools=("test_internet", "ping_gateway"),
    ),
    Category.WIFI_DISCONNECTING: CategorySpec(
        category=Category.WIFI_DISCONNECTING,
        title="Wi-Fi disconnecting",
        keywords=("wifi", "wi-fi", "wireless", "disconnect", "drops",
                  "keeps dropping", "keeps disconnecting"),
        symptoms="Wi-Fi connectivity is intermittent.",
        diagnostic_tools=("get_network_adapters", "get_network_profile",
                          "ping_gateway", "test_dns", "test_internet",
                          "get_network_services_status"),
        remediation_tools=("restart_network_adapter", "renew_ip_configuration",
                           "flush_dns"),
        verification_tools=("test_internet", "ping_gateway"),
    ),
    Category.DNS_PROBLEMS: CategorySpec(
        category=Category.DNS_PROBLEMS,
        title="DNS problems",
        keywords=("dns", "can't resolve", "cannot resolve", "site won't load",
                  "server not found", "webpage"),
        symptoms="Websites fail to resolve although the network is up.",
        diagnostic_tools=("test_dns", "test_internet", "ping_gateway",
                          "get_network_services_status"),
        remediation_tools=("flush_dns", "renew_ip_configuration"),
        verification_tools=("test_dns",),
    ),
    Category.WINDOWS_UPDATE: CategorySpec(
        category=Category.WINDOWS_UPDATE,
        title="Windows Update problems",
        keywords=("windows update", "update", "won't update", "update stuck",
                  "update error", "update failed"),
        symptoms="Windows Update fails or is stuck.",
        diagnostic_tools=("get_windows_update_status", "get_recent_updates",
                          "get_disk_free_space", "get_recent_system_errors"),
        remediation_tools=("restart_windows_update_service", "restart_bits_service",
                           "clear_windows_update_cache_if_safe"),
        verification_tools=("get_windows_update_status",),
    ),
    Category.BLUETOOTH: CategorySpec(
        category=Category.BLUETOOTH,
        title="Bluetooth problems",
        keywords=("bluetooth", "headphones", "pairing", "won't pair", "can't pair"),
        symptoms="Bluetooth devices do not connect or pair.",
        diagnostic_tools=("get_important_services", "get_problem_devices",
                          "get_driver_information"),
        remediation_tools=("restart_bluetooth_service",),
        verification_tools=("get_important_services",),
    ),
    Category.AUDIO: CategorySpec(
        category=Category.AUDIO,
        title="Audio problems",
        keywords=("audio", "sound", "no sound", "speaker", "microphone", "mic",
                  "volume"),
        symptoms="No sound output or audio devices not working.",
        diagnostic_tools=("get_important_services", "get_problem_devices",
                          "get_driver_information"),
        remediation_tools=("restart_audio_service",),
        verification_tools=("get_important_services",),
    ),
    Category.PRINTER: CategorySpec(
        category=Category.PRINTER,
        title="Printer problems",
        keywords=("printer", "print", "can't print", "cannot print", "spooler"),
        symptoms="Printing fails or jobs are stuck.",
        diagnostic_tools=("get_important_services", "get_problem_devices"),
        remediation_tools=("restart_print_spooler",),
        verification_tools=("get_important_services",),
    ),
    Category.APP_CRASHES: CategorySpec(
        category=Category.APP_CRASHES,
        title="Application crashes",
        keywords=("crash", "crashes", "keeps closing", "not responding",
                  "stopped working", "app crash"),
        symptoms="Applications crash or stop responding.",
        diagnostic_tools=("get_recent_application_crashes",
                          "get_recent_application_errors", "get_memory_usage",
                          "get_top_memory_processes"),
        remediation_tools=("terminate_unresponsive_application",),
        verification_tools=("get_memory_usage",),
    ),
    Category.STARTUP_PROBLEMS: CategorySpec(
        category=Category.STARTUP_PROBLEMS,
        title="Windows startup problems",
        keywords=("startup", "boot", "slow to start", "slow boot", "startup slow",
                  "takes long to boot"),
        symptoms="The system is slow to start or boot.",
        diagnostic_tools=("get_startup_apps", "get_boot_time", "get_disk_usage",
                          "get_recent_system_errors"),
        remediation_tools=("clear_safe_temp_files",),
        verification_tools=("get_boot_time",),
    ),
    Category.DEVICE_DRIVER: CategorySpec(
        category=Category.DEVICE_DRIVER,
        title="Device / driver problems",
        keywords=("driver", "device", "not recognized", "device manager",
                  "unknown device", "yellow triangle"),
        symptoms="A hardware device or its driver is malfunctioning.",
        diagnostic_tools=("get_problem_devices", "get_driver_information",
                          "get_recent_system_errors"),
        remediation_tools=(),
        verification_tools=("get_problem_devices",),
    ),
    Category.WINDOWS_SEARCH: CategorySpec(
        category=Category.WINDOWS_SEARCH,
        title="Windows Search problems",
        keywords=("search", "windows search", "start menu search", "can't search",
                  "search not working"),
        symptoms="Windows Search does not return results.",
        diagnostic_tools=("get_important_services", "get_recent_application_errors"),
        remediation_tools=("restart_windows_search",),
        verification_tools=("get_important_services",),
    ),
}


def get_category_spec(category: Category) -> CategorySpec | None:
    return CATEGORIES.get(category)


def classify(problem: str) -> Category:
    """Lightweight offline classifier: score each category by keyword hits.

    Returns the best-matching category, or UNKNOWN if nothing matches.
    """
    text = (problem or "").lower()
    best: tuple[int, Category] = (0, Category.UNKNOWN)
    for spec in CATEGORIES.values():
        score = sum(1 for kw in spec.keywords if kw in text)
        # Weight multi-word keyword matches more heavily.
        score += sum(1 for kw in spec.keywords if " " in kw and kw in text)
        if score > best[0]:
            best = (score, spec.category)
    return best[1]
