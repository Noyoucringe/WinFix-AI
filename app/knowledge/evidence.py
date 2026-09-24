"""Extract typed measurements from raw diagnostic results.

Both the analyzer (before a fix) and the verification engine (after a fix)
read evidence through these functions, so the before/after comparison is like
for like. Every extractor returns ``None`` when the evidence wasn't collected.
"""

from __future__ import annotations

from typing import Any

Results = dict[str, dict[str, Any]]


def data(results: Results, tool: str) -> dict | None:
    r = results.get(tool)
    if r and r.get("success") and isinstance(r.get("data"), dict):
        return r["data"]
    return None


def size_text(mb: float | None) -> str:
    """Human size from megabytes: '96 MB', '2.1 GB'."""
    if mb is None:
        return "—"
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.0f} MB"


def memory(results: Results) -> dict | None:
    d = data(results, "get_memory_usage") or data(results, "get_memory_details")
    if not d:
        return None
    return {"percent": float(d["usage_percent"]), "used_gb": d.get("used_gb"),
            "total_gb": d.get("total_gb"), "available_gb": d.get("available_gb"),
            "swap_percent": d.get("swap_percent")}


def cpu(results: Results) -> dict | None:
    d = data(results, "get_cpu_usage")
    if not d:
        return None
    return {"percent": float(d["usage_percent"]), "speed_mhz": d.get("speed_mhz"),
            "sample_seconds": d.get("sample_seconds", 1)}


def disk(results: Results) -> dict | None:
    d = data(results, "get_disk_free_space") or data(results, "get_disk_usage")
    if not d:
        return None
    percent = d.get("usage_percent")
    free = d.get("free_gb")
    low = d.get("low_space")
    if low is None and percent is not None and free is not None:
        low = percent >= 90 or free < 10
    return {"percent": percent, "free_gb": free, "total_gb": d.get("total_gb"),
            "drive": d.get("drive", "C:"), "low": bool(low)}


def app_groups(results: Results) -> list[dict]:
    d = data(results, "get_running_processes")
    if d and d.get("groups"):
        return d["groups"]
    d = data(results, "get_top_memory_processes")
    if d and d.get("top_memory_apps"):
        return d["top_memory_apps"]
    return []


# Processes that are part of Windows and never "your app".
_SYSTEM_PROCESSES = {
    "system", "system idle process", "registry", "memory compression", "memcompression",
    "svchost.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "smss.exe",
    "dwm.exe", "searchindexer.exe", "msmpeng.exe", "winlogon.exe", "fontdrvhost.exe",
    "systemd", "kthreadd",
}


def top_app(results: Results) -> dict | None:
    """The user-facing app using the most memory."""
    for g in app_groups(results):
        if g["name"].lower() not in _SYSTEM_PROCESSES:
            return g
    return None


def unresponsive_apps(results: Results) -> list[dict]:
    d = data(results, "get_unresponsive_apps")
    if d:
        return d.get("apps", [])
    return [g for g in app_groups(results) if g.get("not_responding")]


def service(results: Results, name: str) -> dict | None:
    for tool in ("get_search_indexer_status", "get_important_services",
                 "get_windows_update_status", "get_network_services_status"):
        d = data(results, tool)
        if not d:
            continue
        if tool == "get_search_indexer_status":
            if name == "WSearch":
                return d.get("service")
            continue
        svc = (d.get("services") or {}).get(name)
        if svc:
            return svc
    return None


def indexer(results: Results) -> dict | None:
    d = data(results, "get_search_indexer_status")
    if d:
        svc = d.get("service") or {}
        return {"memory_mb": d.get("memory_mb", 0.0), "running": bool(svc.get("running")),
                "status_text": svc.get("status_text", "Unknown"),
                "healthy": bool(svc.get("healthy", True)),
                "responding": d.get("responding", True),
                "process_running": d.get("process_running", False)}
    group = next((g for g in app_groups(results)
                  if g["name"].lower() == "searchindexer.exe"), None)
    svc = service(results, "WSearch")
    # Without the indexer process in the list we can't state its memory, so
    # only report when the service itself is in trouble.
    if group is None and (svc is None or svc.get("healthy", True)):
        return None
    return {"memory_mb": group["memory_mb"] if group else 0.0,
            "running": bool(svc and svc.get("running")),
            "status_text": (svc or {}).get("status_text", "Unknown"),
            "healthy": bool((svc or {}).get("healthy", True)),
            "responding": not (group and group.get("not_responding")),
            "process_running": group is not None}


def network(results: Results) -> dict:
    adapters = data(results, "get_network_adapters")
    gw = data(results, "ping_gateway")
    dns = data(results, "test_dns")
    net = data(results, "test_internet")
    return {
        "adapters_up": adapters.get("up_count") if adapters else None,
        "adapters": adapters.get("adapters", []) if adapters else [],
        "gateway": gw.get("gateway") if gw else None,
        "gateway_interface": gw.get("interface") if gw else None,
        "gateway_reachable": gw.get("reachable") if gw else None,
        "gateway_known": bool(gw and gw.get("gateway")),
        "dns_working": dns.get("dns_working") if dns else None,
        "internet": net.get("internet_reachable") if net else None,
    }


def reclaimable(results: Results) -> dict | None:
    d = data(results, "get_reclaimable_space")
    if not d:
        return None
    return {"temp_mb": d.get("temp_mb", 0.0), "recycle_mb": d.get("recycle_bin_mb"),
            "recycle_items": d.get("recycle_bin_items")}


def reboot_pending(results: Results) -> bool | None:
    d = data(results, "get_pending_reboot")
    return None if d is None else bool(d.get("reboot_pending"))


def startup_count(results: Results) -> int | None:
    d = data(results, "get_startup_apps")
    return None if d is None else int(d.get("count", 0))


def uptime_days(results: Results) -> float | None:
    d = data(results, "get_boot_time")
    return None if d is None else float(d.get("uptime_days", 0.0))


def event_count(results: Results, tool: str) -> int | None:
    d = data(results, tool)
    return None if d is None else int(d.get("count", 0))


def bluetooth(results: Results) -> dict | None:
    return data(results, "get_bluetooth_devices")


def problem_devices(results: Results) -> list[dict] | None:
    d = data(results, "get_problem_devices")
    return None if d is None else d.get("devices", [])


def crashes(results: Results) -> dict | None:
    return data(results, "get_recent_application_crashes")


def pick_adapter(results: Results, prefer_wireless: bool = False) -> str | None:
    """The adapter a restart should target: the default-route one, else a real one."""
    net = network(results)
    candidates = [a for a in net["adapters"] if not a.get("virtual")]
    if net["gateway_interface"] and any(a["name"] == net["gateway_interface"]
                                        for a in candidates):
        return net["gateway_interface"]
    if prefer_wireless:
        wireless = [a for a in candidates if a.get("wireless")]
        if wireless:
            return wireless[0]["name"]
    up = [a for a in candidates if a.get("is_up")]
    if len(up) == 1:
        return up[0]["name"]
    return None
