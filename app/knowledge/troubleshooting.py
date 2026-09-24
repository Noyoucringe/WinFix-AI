"""Deterministic, evidence-based analysis.

Turns collected diagnostics into a :class:`Diagnosis`: evidence cards, the
possible causes (each tied to the measurements behind it), a headline, and
notes. This runs with or without an LLM — AI can only rephrase the result,
never invent the facts.

Rules fire only when the evidence crosses a threshold, and several signals
combine rather than one number deciding everything.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.core.models import Category, Cause, Diagnosis, EvidenceCard, Level
from app.knowledge import evidence as ev
from app.knowledge.categories import get_category_spec

Results = ev.Results

MEMORY_HIGH = 70.0
MEMORY_SEVERE = 85.0
CPU_ELEVATED = 60.0
CPU_HIGH = 85.0
INDEXER_MEMORY_MB = 1024.0
RECLAIM_MB = 500.0
STARTUP_MANY = 12
UPTIME_DAYS = 7.0
SYSTEM_ERRORS = 5
CRASHES = 3

_PERF_CATEGORIES = {Category.SLOW_COMPUTER, Category.HIGH_CPU, Category.HIGH_MEMORY,
                    Category.APP_CRASHES, Category.STARTUP_PROBLEMS, Category.UNKNOWN}
_NET_CATEGORIES = {Category.INTERNET_DOWN, Category.WIFI_DISCONNECTING,
                   Category.DNS_PROBLEMS}

# Which service faults are relevant to which problems, and the fix for each.
_SERVICE_RULES: dict[str, tuple[set[Category], str | None]] = {
    "WSearch": ({Category.WINDOWS_SEARCH, Category.SLOW_COMPUTER, Category.HIGH_MEMORY,
                 Category.HIGH_CPU}, "restart_windows_search"),
    "wuauserv": ({Category.WINDOWS_UPDATE}, "restart_windows_update_service"),
    "bits": ({Category.WINDOWS_UPDATE}, "restart_bits_service"),
    "Spooler": ({Category.PRINTER}, "restart_print_spooler"),
    "Audiosrv": ({Category.AUDIO}, "restart_audio_service"),
    "AudioEndpointBuilder": ({Category.AUDIO}, None),
    "bthserv": ({Category.BLUETOOTH}, "restart_bluetooth_service"),
    "WlanSvc": ({Category.WIFI_DISCONNECTING, Category.INTERNET_DOWN},
                "restart_wlan_service"),
    # Protected core services: WinFix reports them but never restarts them.
    "Dnscache": (_NET_CATEGORIES, None),
    "Dhcp": (_NET_CATEGORIES, None),
}

_HEADLINES = {
    "memory_pressure": "Your PC is experiencing memory pressure.",
    "high_cpu": "Your processor is working unusually hard.",
    "search_indexer": "Windows Search isn't working properly.",
    "low_disk": "Your storage is almost full.",
    "temp_files": "Temporary files are taking up space.",
    "recycle_bin": "The Recycle Bin is taking up space.",
    "no_adapter": "Your PC isn't connected to a network.",
    "gateway_unreachable": "Your PC can't reach your router.",
    "no_gateway": "Your PC didn't get a network address.",
    "dns_failure": "Websites can't be found.",
    "internet_unreachable": "Your router is reachable, but the internet isn't.",
    "update_disabled": "Windows Update is turned off.",
    "reboot_pending": "Windows is waiting for a restart to finish updating.",
    "update_space": "There isn't enough free space for updates.",
    "bt_missing": "No Bluetooth adapter was found.",
    "bt_problem": "Your Bluetooth adapter reports a problem.",
    "device_problem": "A device on your PC reports a problem.",
    "app_crashes": "An app has been crashing repeatedly.",
    "unresponsive": "An app on your PC isn't responding.",
    "many_startup": "Many apps start when you sign in.",
}

# Short names for History's "Diagnosis" column.
SHORT_LABELS = {
    "memory_pressure": "Memory pressure",
    "high_cpu": "High CPU usage",
    "search_indexer": "Windows Search indexer issue",
    "large_apps": "Large background apps",
    "low_disk": "Low disk space",
    "temp_files": "Temporary files",
    "recycle_bin": "Recycle Bin",
    "no_adapter": "No network connection",
    "gateway_unreachable": "Router not responding",
    "no_gateway": "No network address",
    "dns_failure": "DNS not resolving",
    "internet_unreachable": "Internet provider issue",
    "update_disabled": "Windows Update disabled",
    "reboot_pending": "Restart required to finish updates",
    "update_space": "Not enough space for updates",
    "bt_missing": "No Bluetooth adapter",
    "bt_problem": "Bluetooth adapter problem",
    "device_problem": "Device problem",
    "app_crashes": "App crashes",
    "unresponsive": "App not responding",
    "many_startup": "High-impact startup apps",
    "system_errors": "System errors",
    "long_uptime": "Long time since restart",
}


def short_label(cause: Cause) -> str:
    if cause.id in SHORT_LABELS:
        return SHORT_LABELS[cause.id]
    if cause.id.startswith("service:"):
        return cause.cause.replace(" isn't running", " not running")
    return cause.cause


Rule = Callable[[Results, Category], list[Cause]]


# --- rules -----------------------------------------------------------------
def _memory(results: Results, category: Category) -> list[Cause]:
    m = ev.memory(results)
    if not m or m["percent"] < MEMORY_HIGH:
        return []
    severe = m["percent"] >= MEMORY_SEVERE
    evidence = [f"Memory in use: {m['percent']:.1f}%"]
    if m.get("used_gb") and m.get("total_gb"):
        evidence.append(f"{m['used_gb']:.1f} GB of {m['total_gb']:.1f} GB used")
    return [Cause(
        id="memory_pressure",
        cause="Very high memory utilization" if severe else "High memory utilization",
        confidence=0.85 if severe else 0.75,
        level=Level.CRITICAL if severe else Level.CAUTION,
        detail=(f"Supported by current system measurements: {m['percent']:.1f}% of "
                "memory is in use."),
        evidence=evidence, sources=["get_memory_usage"])]


def _search_indexer(results: Results, category: Category) -> list[Cause]:
    idx = ev.indexer(results)
    if not idx or category not in _SERVICE_RULES["WSearch"][0]:
        return []
    size = ev.size_text(idx["memory_mb"])
    if not idx["responding"]:
        title = "Windows Search indexer isn't responding"
        detail = (f"The Windows Search indexer isn't responding and is still holding "
                  f"{size} of memory.")
    elif not idx["running"] and not idx["healthy"]:
        title = "Windows Search isn't running"
        detail = ("The Windows Search service is stopped even though it's set to "
                  "start automatically.")
    elif idx["memory_mb"] >= INDEXER_MEMORY_MB:
        title = "Windows Search indexer is using unusual memory"
        detail = f"The indexer is holding {size} of memory; it normally uses far less."
    else:
        return []
    return [Cause(id="search_indexer", cause=title, detail=detail,
                  confidence=0.7, level=Level.CAUTION,
                  remediation="restart_windows_search",
                  evidence=[f"SearchIndexer.exe memory: {size}",
                            f"Windows Search service: {idx['status_text']}"],
                  sources=["get_search_indexer_status", "get_running_processes",
                           "get_important_services"])]


def _large_apps(results: Results, category: Category) -> list[Cause]:
    m = ev.memory(results)
    app = ev.top_app(results)
    if not m or not app or m["percent"] < MEMORY_HIGH:
        return []
    total_mb = (m.get("total_gb") or 0) * 1024
    if app["memory_mb"] < max(1536.0, 0.15 * total_mb):
        return []
    size = ev.size_text(app["memory_mb"])
    return [Cause(id="large_apps", cause="Large background applications",
                  detail=(f"Several applications are consuming significant memory. "
                          f"{app['display_name']} alone is using {size}."),
                  confidence=0.55, level=Level.INFO,
                  evidence=[f"{app['display_name']}: {size} across {app['count']} "
                            f"process{'es' if app['count'] != 1 else ''}"],
                  sources=["get_running_processes"])]


def _cpu(results: Results, category: Category) -> list[Cause]:
    c = ev.cpu(results)
    if not c or c["percent"] < CPU_ELEVATED:
        return []
    high = c["percent"] >= CPU_HIGH
    groups = sorted(ev.app_groups(results), key=lambda g: g["cpu_percent"], reverse=True)
    top = groups[0] if groups else None
    detail = f"The processor was {c['percent']:.0f}% busy when measured."
    if top and top["cpu_percent"] >= 10:
        detail += f" {top['display_name']} was using {top['cpu_percent']:.0f}%."
    return [Cause(id="high_cpu", cause="High CPU usage" if high else "Elevated CPU usage",
                  detail=detail, confidence=0.7 if high else 0.45,
                  level=Level.CAUTION, evidence=[f"CPU utilization: {c['percent']:.1f}%"],
                  sources=["get_cpu_usage", "get_running_processes"])]


def _disk(results: Results, category: Category) -> list[Cause]:
    d = ev.disk(results)
    causes: list[Cause] = []
    if d and d["low"]:
        critical = (d["percent"] or 0) >= 95 or (d["free_gb"] or 99) < 5
        causes.append(Cause(
            id="low_disk", cause=f"Low free space on {d['drive']}",
            detail=(f"Only {d['free_gb']:.1f} GB is free on {d['drive']} "
                    f"({d['percent']:.1f}% used)."),
            confidence=0.85, level=Level.CRITICAL if critical else Level.CAUTION,
            evidence=[f"Free space: {d['free_gb']:.1f} GB", f"Used: {d['percent']:.1f}%"],
            sources=["get_disk_free_space", "get_disk_usage"]))
    wants_space = (d and d["low"]) or category == Category.LOW_DISK_SPACE
    r = ev.reclaimable(results)
    if r and wants_space:
        if r["temp_mb"] >= RECLAIM_MB:
            causes.append(Cause(
                id="temp_files", cause="Temporary files",
                detail=f"Temporary files are using {ev.size_text(r['temp_mb'])}.",
                confidence=0.7, level=Level.CAUTION, remediation="clear_safe_temp_files",
                evidence=[f"Temporary files: {ev.size_text(r['temp_mb'])}"],
                sources=["get_reclaimable_space"]))
        if r["recycle_mb"] and r["recycle_mb"] >= RECLAIM_MB:
            causes.append(Cause(
                id="recycle_bin", cause="Files in the Recycle Bin",
                detail=(f"The Recycle Bin holds {ev.size_text(r['recycle_mb'])} in "
                        f"{r['recycle_items']} items."),
                confidence=0.6, level=Level.CAUTION, remediation="empty_recycle_bin",
                evidence=[f"Recycle Bin: {ev.size_text(r['recycle_mb'])}"],
                sources=["get_reclaimable_space"]))
    if category == Category.WINDOWS_UPDATE and d and (d["free_gb"] or 99) < 10:
        causes.append(Cause(
            id="update_space", cause="Not enough free space for updates",
            detail=(f"Feature updates need about 10 GB free; {d['drive']} has "
                    f"{d['free_gb']:.1f} GB."),
            confidence=0.7, level=Level.CAUTION, remediation="clear_safe_temp_files",
            evidence=[f"Free space: {d['free_gb']:.1f} GB"],
            sources=["get_disk_free_space"]))
    return causes


def _network(results: Results, category: Category) -> list[Cause]:
    if category not in _NET_CATEGORIES:
        return []
    n = ev.network(results)
    fix_adapter = ("restart_wlan_service" if category == Category.WIFI_DISCONNECTING
                   else "restart_network_adapter")
    if n["adapters_up"] == 0:
        return [Cause(id="no_adapter", cause="No network adapter is connected",
                      detail="None of your PC's network adapters has an active link.",
                      confidence=0.85, level=Level.CRITICAL, remediation=fix_adapter,
                      evidence=["Connected adapters: 0"],
                      sources=["get_network_adapters"])]
    causes: list[Cause] = []
    if n["gateway_reachable"] is False and n["gateway_known"]:
        causes.append(Cause(
            id="gateway_unreachable", cause="Your router isn't responding",
            detail=f"Your PC sent requests to your router ({n['gateway']}) and got no reply.",
            confidence=0.75, level=Level.CRITICAL, remediation="restart_network_adapter",
            evidence=["Router replies: 0"], sources=["ping_gateway"]))
    elif n["gateway_reachable"] is False and not n["gateway_known"]:
        causes.append(Cause(
            id="no_gateway", cause="No network address from a router",
            detail="Your PC doesn't have a route to a router, so it can't get online.",
            confidence=0.7, level=Level.CRITICAL, remediation="renew_ip_configuration",
            evidence=["Default gateway: none"], sources=["ping_gateway"]))
    if n["dns_working"] is False and n["gateway_reachable"] is not False:
        causes.append(Cause(
            id="dns_failure", cause="Website names aren't resolving (DNS)",
            detail="Your network is up, but website names couldn't be turned into addresses.",
            confidence=0.75, level=Level.CAUTION, remediation="flush_dns",
            evidence=["DNS lookups failed"], sources=["test_dns"]))
    if (n["internet"] is False and n["gateway_reachable"] is True
            and n["dns_working"] is not False):
        causes.append(Cause(
            id="internet_unreachable", cause="The internet is unreachable beyond your router",
            detail=("Your router responds, but connections to the internet fail. This "
                    "usually points to your router or internet provider."),
            confidence=0.55, level=Level.CAUTION,
            evidence=["Router: reachable", "Internet: unreachable"],
            sources=["test_internet", "ping_gateway"]))
    return causes


def _services(results: Results, category: Category) -> list[Cause]:
    causes: list[Cause] = []
    for name, (categories, fix) in _SERVICE_RULES.items():
        if category not in categories or name == "WSearch":
            continue  # WSearch is covered by the indexer rule
        svc = ev.service(results, name)
        if not svc or svc.get("healthy", True):
            continue
        label = svc.get("label", name)
        if svc.get("start_type") == "disabled":
            causes.append(Cause(
                id="update_disabled" if name == "wuauserv" else f"service_disabled:{name}",
                cause=f"{label} is disabled",
                detail=(f"The {label} service has been turned off. WinFix won't re-enable "
                        "a disabled service for you."),
                confidence=0.75, level=Level.CAUTION,
                evidence=[f"{name} start type: disabled"],
                sources=["get_important_services", "get_windows_update_status"]))
            continue
        causes.append(Cause(
            id=f"service:{name}", cause=f"{label} isn't running",
            detail=f"The {label} service is {svc.get('status_text', 'stopped').lower()}.",
            confidence=0.8, level=Level.CAUTION, remediation=fix,
            evidence=[f"{name}: {svc.get('status_text')}"],
            sources=["get_important_services", "get_windows_update_status",
                     "get_network_services_status"]))
    return causes


def _updates(results: Results, category: Category) -> list[Cause]:
    pending = ev.reboot_pending(results)
    if not pending:
        return []
    relevant = category == Category.WINDOWS_UPDATE
    return [Cause(id="reboot_pending", cause="Restart required to finish updates",
                  detail="Windows has installed updates that finish when you restart.",
                  confidence=0.8 if relevant else 0.4,
                  level=Level.CAUTION if relevant else Level.INFO,
                  evidence=["Windows Update: restart pending"],
                  sources=["get_pending_reboot"])]


def _bluetooth(results: Results, category: Category) -> list[Cause]:
    if category != Category.BLUETOOTH:
        return []
    bt = ev.bluetooth(results)
    if not bt:
        return []
    if not bt.get("adapter_present"):
        return [Cause(id="bt_missing", cause="No Bluetooth adapter was found",
                      detail=("Windows doesn't see a Bluetooth radio. It may be turned off, "
                              "in airplane mode, or missing a driver."),
                      confidence=0.75, level=Level.CRITICAL,
                      evidence=["Bluetooth devices: 0"], sources=["get_bluetooth_devices"])]
    if bt.get("problem_count"):
        bad = [d["name"] for d in bt["devices"] if d.get("status") not in ("OK", None)]
        return [Cause(id="bt_problem", cause="A Bluetooth device reports a problem",
                      detail=f"{', '.join(bad[:2])} reports an error in Device Manager.",
                      confidence=0.65, level=Level.CAUTION,
                      evidence=[f"Bluetooth devices with problems: {bt['problem_count']}"],
                      sources=["get_bluetooth_devices"])]
    return []


def _devices(results: Results, category: Category) -> list[Cause]:
    if category not in (Category.DEVICE_DRIVER, Category.AUDIO, Category.PRINTER):
        return []
    devices = ev.problem_devices(results)
    if not devices:
        return []
    names = ", ".join(d["name"] for d in devices[:2])
    return [Cause(id="device_problem", cause=f"{len(devices)} device(s) report a problem",
                  detail=f"Device Manager reports an error for {names}.",
                  confidence=0.65, level=Level.CAUTION,
                  evidence=[f"{d['name']}: {d.get('status')}" for d in devices[:3]],
                  sources=["get_problem_devices"])]


def _apps(results: Results, category: Category) -> list[Cause]:
    causes: list[Cause] = []
    # The indexer has its own cause and fix; don't report it twice.
    hung = [a for a in ev.unresponsive_apps(results)
            if (a.get("name") or "").lower() != "searchindexer.exe"]
    if hung and category in _PERF_CATEGORIES:
        name = hung[0].get("display_name") or hung[0].get("name")
        causes.append(Cause(id="unresponsive", cause=f"{name} isn't responding",
                            detail=f"Windows reports that {name} has stopped responding.",
                            confidence=0.6, level=Level.CAUTION,
                            evidence=[f"Not responding: {name}"],
                            sources=["get_unresponsive_apps", "get_running_processes"]))
    crashes = ev.crashes(results)
    if crashes and crashes.get("count", 0) >= CRASHES and crashes.get("apps"):
        top = crashes["apps"][0]
        causes.append(Cause(id="app_crashes", cause=f"{top['name']} keeps crashing",
                            detail=(f"{top['name']} crashed {top['crashes']} times in the "
                                    "last 7 days."),
                            confidence=0.7, level=Level.CAUTION,
                            evidence=[f"Crashes this week: {crashes['count']}"],
                            sources=["get_recent_application_crashes"]))
    return causes


def _background(results: Results, category: Category) -> list[Cause]:
    causes: list[Cause] = []
    startup = ev.startup_count(results)
    if startup is not None and startup >= STARTUP_MANY:
        causes.append(Cause(id="many_startup", cause="Many apps start with Windows",
                            detail=f"{startup} apps start automatically when you sign in.",
                            confidence=0.65 if category == Category.STARTUP_PROBLEMS else 0.4,
                            level=Level.CAUTION if category == Category.STARTUP_PROBLEMS
                            else Level.INFO,
                            evidence=[f"Startup apps: {startup}"],
                            sources=["get_startup_apps"]))
    days = ev.uptime_days(results)
    if days is not None and days >= UPTIME_DAYS:
        causes.append(Cause(id="long_uptime",
                            cause=f"Your PC hasn't restarted in {days:.0f} days",
                            detail="Restarting clears memory and finishes pending updates.",
                            confidence=0.35, level=Level.INFO,
                            evidence=[f"Uptime: {days:.1f} days"], sources=["get_boot_time"]))
    errors = ev.event_count(results, "get_recent_system_errors")
    if errors is not None and errors >= SYSTEM_ERRORS:
        d = ev.data(results, "get_recent_system_errors") or {}
        source = (d.get("top_sources") or [{}])[0].get("source")
        detail = f"{errors} errors were logged in the last 24 hours"
        detail += f", most from {source}." if source else "."
        causes.append(Cause(id="system_errors", cause="Recent system errors",
                            detail=detail, confidence=0.35, level=Level.INFO,
                            evidence=[f"System errors (24h): {errors}"],
                            sources=["get_recent_system_errors"]))
    return causes


RULES: tuple[Rule, ...] = (_memory, _search_indexer, _large_apps, _cpu, _disk, _network,
                           _services, _updates, _bluetooth, _devices, _apps, _background)


# --- evidence cards --------------------------------------------------------
def _level_for(value: float, caution: float, critical: float) -> Level:
    if value >= critical:
        return Level.CRITICAL
    return Level.CAUTION if value >= caution else Level.OK


def _memory_card(results: Results) -> EvidenceCard | None:
    m = ev.memory(results)
    if not m:
        return None
    level = _level_for(m["percent"], MEMORY_HIGH, MEMORY_SEVERE)
    return EvidenceCard(
        key="memory", label="Memory", icon="memory", value=f"{m['percent']:.1f}%",
        detail=(f"{m['used_gb']:.1f} GB / {m['total_gb']:.1f} GB used"
                if m.get("used_gb") is not None and m.get("total_gb") else "In use"),
        level=level, progress=m["percent"] / 100,
        status_text={Level.OK: "Normal", Level.CAUTION: "High",
                     Level.CRITICAL: "Very high"}[level],
        source="Performance counters")


def _cpu_card(results: Results) -> EvidenceCard | None:
    c = ev.cpu(results)
    if not c:
        return None
    level = _level_for(c["percent"], CPU_ELEVATED, CPU_HIGH)
    return EvidenceCard(
        key="cpu", label="CPU", icon="cpu", value=f"{c['percent']:.1f}%",
        detail=f"Measured over {c['sample_seconds']} second", level=level,
        progress=c["percent"] / 100,
        status_text={Level.OK: "Normal utilization", Level.CAUTION: "Elevated",
                     Level.CRITICAL: "High"}[level],
        source="Performance counters")


def _disk_card(results: Results) -> EvidenceCard | None:
    d = ev.disk(results)
    if not d or d["percent"] is None or d["free_gb"] is None:
        return None
    level = (Level.CRITICAL if d["percent"] >= 95 or d["free_gb"] < 5
             else Level.CAUTION if d["low"] else Level.OK)
    return EvidenceCard(
        key="disk", label="Disk", icon="disk", value=f"{d['percent']:.1f}%",
        detail=f"{d['free_gb']:.1f} GB free on {d['drive']}", level=level,
        progress=d["percent"] / 100,
        status_text={Level.OK: "Enough free space", Level.CAUTION: "Low on space",
                     Level.CRITICAL: "Almost full"}[level],
        source="File system")


def _top_app_card(results: Results) -> EvidenceCard | None:
    app = ev.top_app(results)
    if not app:
        return None
    count = app["count"]
    return EvidenceCard(
        key="top_app", label="Top memory process", icon="list", value=app["display_name"],
        detail=(f"{ev.size_text(app['memory_mb'])} across {count} "
                f"process{'es' if count != 1 else ''}"),
        level=Level.INFO, status_text="Largest app in memory", source="Process list")


def _indexer_card(results: Results) -> EvidenceCard | None:
    idx = ev.indexer(results)
    if not idx:
        return None
    if not idx["responding"]:
        level, text = Level.CAUTION, "Not responding"
    elif not idx["running"] and not idx["healthy"]:
        level, text = Level.CAUTION, "Not running"
    elif idx["memory_mb"] >= INDEXER_MEMORY_MB:
        level, text = Level.CAUTION, "Using unusual memory"
    else:
        level, text = Level.OK, "Running normally" if idx["running"] else idx["status_text"]
    return EvidenceCard(
        key="indexer", label="Windows Search indexer", icon="search",
        value=ev.size_text(idx["memory_mb"]), detail="SearchIndexer.exe",
        level=level, status_text=text, source="Service Control Manager")


def _service_card(results: Results, name: str, label: str, icon: str) -> EvidenceCard | None:
    svc = ev.service(results, name)
    if not svc:
        return None
    healthy = svc.get("healthy", True)
    return EvidenceCard(
        key=f"svc_{name}", label=label, icon=icon, value=svc.get("status_text", "Unknown"),
        detail=f"Service: {name}", level=Level.OK if healthy else Level.CAUTION,
        status_text="Healthy" if healthy else "Needs attention",
        source="Service Control Manager")


def _network_cards(results: Results) -> list[EvidenceCard]:
    n = ev.network(results)
    cards = []
    if n["adapters_up"] is not None:
        ok = n["adapters_up"] > 0
        cards.append(EvidenceCard(
            key="adapter", label="Network adapter", icon="wifi",
            value="Connected" if ok else "Not connected",
            detail=f"{n['adapters_up']} active adapter(s)",
            level=Level.OK if ok else Level.CRITICAL,
            status_text="Link up" if ok else "No link", source="IP Helper API"))

    def _bool_card(key, label, icon, value, good, bad, detail):
        if value is None:
            return
        cards.append(EvidenceCard(key=key, label=label, icon=icon,
                                  value=good if value else bad, detail=detail,
                                  level=Level.OK if value else Level.CRITICAL,
                                  status_text="Working" if value else "Failing",
                                  source="Network test"))

    _bool_card("router", "Router", "router", n["gateway_reachable"], "Reachable",
               "No reply", n["gateway"] or "No default gateway")
    _bool_card("dns", "DNS", "globe", n["dns_working"], "Resolving", "Not resolving",
               "Website name lookups")
    _bool_card("internet", "Internet", "globe", n["internet"], "Reachable", "Unreachable",
               "Connection to the internet")
    return cards


def _storage_cards(results: Results) -> list[EvidenceCard]:
    cards = [c for c in (_disk_card(results),) if c]
    r = ev.reclaimable(results)
    if r:
        cards.append(EvidenceCard(
            key="temp", label="Temporary files", icon="delete",
            value=ev.size_text(r["temp_mb"]), detail="In the TEMP folders",
            level=Level.CAUTION if r["temp_mb"] >= RECLAIM_MB else Level.OK,
            status_text="Can be cleaned" if r["temp_mb"] >= RECLAIM_MB else "Small",
            source="File system"))
        if r["recycle_mb"] is not None:
            cards.append(EvidenceCard(
                key="recycle", label="Recycle Bin", icon="delete",
                value=ev.size_text(r["recycle_mb"]),
                detail=f"{r['recycle_items'] or 0} items",
                level=Level.CAUTION if r["recycle_mb"] >= RECLAIM_MB else Level.OK,
                status_text="Can be emptied" if r["recycle_mb"] >= RECLAIM_MB else "Small",
                source="Shell API"))
    return cards


def _cards(category: Category, results: Results) -> list[EvidenceCard]:
    builders: list[EvidenceCard | None]
    if category in _NET_CATEGORIES:
        return _network_cards(results)
    if category == Category.LOW_DISK_SPACE:
        return _storage_cards(results)
    if category == Category.WINDOWS_UPDATE:
        cards = [_service_card(results, "wuauserv", "Windows Update", "update"),
                 _service_card(results, "bits", "Update downloads (BITS)", "update")]
        pending = ev.reboot_pending(results)
        if pending is not None:
            cards.append(EvidenceCard(
                key="reboot", label="Restart", icon="restart",
                value="Pending" if pending else "Not needed", detail="To finish updates",
                level=Level.CAUTION if pending else Level.OK,
                status_text="Restart required" if pending else "Up to date",
                source="Registry (read-only)"))
        cards.append(_disk_card(results))
        return [c for c in cards if c]
    if category == Category.BLUETOOTH:
        bt = ev.bluetooth(results)
        cards = [_service_card(results, "bthserv", "Bluetooth service", "bluetooth")]
        if bt is not None:
            cards.insert(0, EvidenceCard(
                key="bt", label="Bluetooth adapter", icon="bluetooth",
                value="Found" if bt.get("adapter_present") else "Not found",
                detail=f"{bt.get('count', 0)} Bluetooth devices",
                level=Level.OK if bt.get("adapter_present") else Level.CRITICAL,
                status_text=("Turned off or missing" if not bt.get("adapter_present")
                             else "No problems" if not bt.get("problem_count")
                             else f"{bt['problem_count']} with problems"),
                source="Plug and Play manager"))
        return [c for c in cards if c]
    if category == Category.AUDIO:
        return [c for c in (_service_card(results, "Audiosrv", "Windows Audio", "speaker"),
                            _service_card(results, "AudioEndpointBuilder",
                                          "Audio Endpoint Builder", "speaker")) if c]
    if category == Category.PRINTER:
        return [c for c in (_service_card(results, "Spooler", "Print Spooler", "print"),)
                if c]
    if category == Category.WINDOWS_SEARCH:
        return [c for c in (_indexer_card(results), _memory_card(results)) if c]
    if category == Category.DEVICE_DRIVER:
        devices = ev.problem_devices(results)
        if devices is None:
            return []
        return [EvidenceCard(key="devices", label="Devices with problems", icon="device",
                             value=str(len(devices)),
                             detail=devices[0]["name"] if devices else "Device Manager",
                             level=Level.CAUTION if devices else Level.OK,
                             status_text="Needs attention" if devices else "All working",
                             source="Plug and Play manager")]
    builders = [_memory_card(results), _cpu_card(results), _disk_card(results),
                _top_app_card(results), _indexer_card(results)]
    if category == Category.STARTUP_PROBLEMS:
        startup = ev.startup_count(results)
        if startup is not None:
            builders.insert(0, EvidenceCard(
                key="startup", label="Startup apps", icon="rocket", value=str(startup),
                detail="Start when you sign in",
                level=Level.CAUTION if startup >= STARTUP_MANY else Level.OK,
                status_text="Many" if startup >= STARTUP_MANY else "Normal", source="WMI"))
    return [c for c in builders if c]


# --- notes (things WinFix won't do, but you can) ---------------------------
def _notes(causes: list[Cause], results: Results) -> list[str]:
    notes = []
    ids = {c.id for c in causes}
    app = ev.top_app(results)
    if "large_apps" in ids and app:
        notes.append(f"{app['display_name']} is also using {ev.size_text(app['memory_mb'])}. "
                     "Closing tabs or windows you don't need frees more memory. "
                     "WinFix never closes your apps.")
    if "unresponsive" in ids:
        notes.append("WinFix never closes your apps. If an app stays frozen, close it from "
                     "Task Manager (Ctrl+Shift+Esc).")
    if "many_startup" in ids:
        notes.append("You can turn off startup apps you don't need in Settings > Apps > "
                     "Startup.")
    if "reboot_pending" in ids or "long_uptime" in ids:
        notes.append("Restart your PC when it's convenient. WinFix won't restart it for you.")
    if "internet_unreachable" in ids:
        notes.append("Try restarting your router. If that doesn't help, contact your "
                     "internet provider.")
    if "device_problem" in ids or "bt_problem" in ids:
        notes.append("Check Windows Update > Advanced options > Optional updates for a "
                     "newer driver.")
    if any(i.startswith("service_disabled") or i == "update_disabled" for i in ids):
        notes.append("A disabled service was turned off on purpose or by another app. "
                     "WinFix leaves that setting alone.")
    return notes


# --- entry point -------------------------------------------------------------
def analyze(category: Category, results: Results) -> Diagnosis:
    causes: list[Cause] = []
    for rule in RULES:
        causes.extend(rule(results, category))
    order = {Level.CRITICAL: 0, Level.CAUTION: 1, Level.INFO: 2, Level.OK: 3}
    causes.sort(key=lambda c: (order[c.level], -c.confidence))

    problems = [c for c in causes if c.level in (Level.CAUTION, Level.CRITICAL)]
    if problems:
        top = problems[0]
        headline = _HEADLINES.get(top.id) or _service_headline(top) or f"{top.cause}."
        level = Level.CRITICAL if any(c.level == Level.CRITICAL for c in problems) \
            else Level.CAUTION
        linked = next((c for c in problems if c.remediation and c is not top), None)
        summary = headline + " " + (linked.detail if linked else top.detail)
    else:
        level = Level.OK
        headline = "WinFix didn't find a problem in these checks."
        summary = ("The measurements taken on your PC look normal. If the problem happens "
                   "again, run the checks while it's happening.")

    spec = get_category_spec(category)
    successful = sum(1 for r in results.values() if r.get("success"))
    return Diagnosis(
        category=category,
        headline=headline,
        short_label=short_label(problems[0]) if problems else "No problem found",
        summary=summary.strip(),
        level=level,
        possible_causes=causes,
        evidence_cards=_cards(category, results),
        notes=_notes(causes, results),
        recommended_tools=list(spec.remediation_tools) if spec else [],
        analysis_source="local",
        checks_completed=successful,
        completed_at=datetime.now(timezone.utc),
    )


def _service_headline(cause: Cause) -> str | None:
    if cause.id.startswith("service:"):
        return f"{cause.cause}."
    return None
