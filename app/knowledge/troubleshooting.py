"""Offline evidence interpretation.

Turns collected diagnostic results into an evidence-backed :class:`Diagnosis`
without an LLM. This is the deterministic baseline analyzer: it always runs, so
the product is useful even when no AI backend is configured.

Interpretation combines *multiple* signals and expresses uncertainty via
confidence scores — it never does single-condition diagnosis.
"""

from __future__ import annotations

from typing import Any

from app.core.models import Category, Cause, Diagnosis
from app.knowledge.categories import get_category_spec

ToolResults = dict[str, dict[str, Any]]


def _data(results: ToolResults, tool: str) -> dict | None:
    r = results.get(tool)
    if r and r.get("success"):
        return r.get("data")
    return None


def _mem_causes(results: ToolResults) -> list[Cause]:
    causes: list[Cause] = []
    mem = _data(results, "get_memory_usage")
    if not mem:
        return causes
    pct = mem.get("usage_percent", 0)
    evidence = [f"Memory utilization: {pct}%",
                f"Available memory: {mem.get('available_gb', '?')} GB"]
    top = _data(results, "get_top_memory_processes")
    if top and top.get("top_memory_processes"):
        p = top["top_memory_processes"][0]
        evidence.append(f"Top memory process: {p['name']} — {p['memory_mb']} MB")
    if pct >= 90:
        causes.append(Cause(cause="Severe memory pressure", confidence=0.85,
                            evidence=evidence))
    elif pct >= 75:
        causes.append(Cause(cause="Elevated memory usage", confidence=0.6,
                            evidence=evidence))
    if mem.get("swap_percent", 0) >= 50:
        causes.append(Cause(cause="Heavy swap/paging activity", confidence=0.55,
                            evidence=[f"Swap usage: {mem.get('swap_percent')}%"]))
    return causes


def _cpu_causes(results: ToolResults) -> list[Cause]:
    causes: list[Cause] = []
    cpu = _data(results, "get_cpu_usage")
    if not cpu:
        return causes
    pct = cpu.get("usage_percent", 0)
    evidence = [f"CPU utilization: {pct}%"]
    top = _data(results, "get_top_cpu_processes")
    if top and top.get("top_cpu_processes"):
        p = top["top_cpu_processes"][0]
        evidence.append(f"Top CPU process: {p['name']} — {p['cpu_percent']}%")
    if pct >= 85:
        causes.append(Cause(cause="Sustained high CPU usage", confidence=0.8,
                            evidence=evidence))
    elif pct >= 60:
        causes.append(Cause(cause="Moderately high CPU usage", confidence=0.5,
                            evidence=evidence))
    return causes


def _disk_causes(results: ToolResults) -> list[Cause]:
    causes: list[Cause] = []
    disk = _data(results, "get_disk_usage") or _data(results, "get_disk_free_space")
    if not disk:
        return causes
    pct = disk.get("usage_percent")
    free = disk.get("free_gb")
    evidence = []
    if pct is not None:
        evidence.append(f"Disk usage: {pct}%")
    if free is not None:
        evidence.append(f"Free space: {free} GB")
    low = disk.get("low_space") or (pct is not None and pct >= 90) or (
        free is not None and free < 5)
    if low:
        causes.append(Cause(cause="Low free disk space", confidence=0.85,
                            evidence=evidence or ["Disk is nearly full"]))
    return causes


def _network_causes(results: ToolResults) -> list[Cause]:
    causes: list[Cause] = []
    internet = _data(results, "test_internet")
    dns = _data(results, "test_dns")
    gw = _data(results, "ping_gateway")

    gw_ok = bool(gw and gw.get("reachable"))
    net_ok = bool(internet and internet.get("internet_reachable"))
    dns_ok = bool(dns and dns.get("dns_working"))

    if gw and not gw_ok:
        causes.append(Cause(
            cause="Cannot reach the local gateway (local network issue)",
            confidence=0.75,
            evidence=[f"Gateway {gw.get('gateway')} unreachable"]))
    if dns is not None and not dns_ok and gw_ok:
        causes.append(Cause(
            cause="DNS resolution is failing",
            confidence=0.7,
            evidence=[f"Resolved {dns.get('resolved_count', 0)}/{dns.get('total', 0)} hosts"]))
    if internet is not None and not net_ok and gw_ok and dns_ok:
        causes.append(Cause(
            cause="Internet unreachable despite working local network and DNS",
            confidence=0.6,
            evidence=["Outbound connectivity test failed"]))
    return causes


def _service_causes(results: ToolResults, service_names: list[str]) -> list[Cause]:
    causes: list[Cause] = []
    for tool in ("get_important_services", "get_windows_update_status",
                 "get_network_services_status"):
        data = _data(results, tool)
        if not data:
            continue
        services = data.get("services", {})
        for name in service_names:
            svc = services.get(name)
            if svc and svc.get("running") is False:
                causes.append(Cause(
                    cause=f"The {svc.get('label', name)} service is not running",
                    confidence=0.8,
                    evidence=[f"{name} status: {svc.get('status')}"]))
    return causes


def _device_causes(results: ToolResults) -> list[Cause]:
    causes: list[Cause] = []
    dev = _data(results, "get_problem_devices")
    if dev and dev.get("raw") and dev["raw"] not in ("", "[]", "null"):
        causes.append(Cause(cause="One or more devices report an error state",
                            confidence=0.6,
                            evidence=["Device Manager reports non-OK devices"]))
    return causes


def analyze(category: Category, results: ToolResults) -> Diagnosis:
    """Produce an evidence-backed diagnosis from collected diagnostics."""
    spec = get_category_spec(category)
    causes: list[Cause] = []

    if category in (Category.SLOW_COMPUTER, Category.STARTUP_PROBLEMS):
        causes += _cpu_causes(results) + _mem_causes(results) + _disk_causes(results)
    elif category == Category.HIGH_CPU:
        causes += _cpu_causes(results)
    elif category == Category.HIGH_MEMORY:
        causes += _mem_causes(results)
    elif category == Category.LOW_DISK_SPACE:
        causes += _disk_causes(results)
    elif category in (Category.INTERNET_DOWN, Category.WIFI_DISCONNECTING,
                      Category.DNS_PROBLEMS):
        causes += _network_causes(results)
        causes += _service_causes(results, ["Dnscache", "Dhcp", "WlanSvc"])
    elif category == Category.WINDOWS_UPDATE:
        causes += _service_causes(results, ["wuauserv", "bits"])
        causes += _disk_causes(results)
    elif category == Category.BLUETOOTH:
        causes += _service_causes(results, ["bthserv"]) + _device_causes(results)
    elif category == Category.AUDIO:
        causes += _service_causes(results, ["Audiosrv"]) + _device_causes(results)
    elif category == Category.PRINTER:
        causes += _service_causes(results, ["Spooler"])
    elif category == Category.WINDOWS_SEARCH:
        causes += _service_causes(results, ["WSearch"])
    elif category == Category.DEVICE_DRIVER:
        causes += _device_causes(results)
    elif category == Category.APP_CRASHES:
        causes += _mem_causes(results)

    causes.sort(key=lambda c: c.confidence, reverse=True)

    if causes:
        top = causes[0]
        summary = _summary_for(category, top)
    else:
        summary = (
            "Diagnostics completed but did not surface a strong signal. "
            "The evidence does not clearly point to a single cause."
        )

    return Diagnosis(
        category=category,
        summary=summary,
        possible_causes=causes,
        recommended_tools=list(spec.remediation_tools) if spec else [],
        analysis_source="local",
    )


def _summary_for(category: Category, top: Cause) -> str:
    return f"{top.cause} appears {top.likelihood_word} to be contributing to the problem."
