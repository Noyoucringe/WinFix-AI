"""Performance diagnostics: CPU, memory, disk activity and processes (read-only)."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path

import psutil

from app.core import winapi
from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool

_GB = 1024 ** 3
_MB = 1024 ** 2

# Friendly names for well-known system processes whose file description is
# missing or unhelpful. Anything else uses the executable's own description.
_KNOWN_NAMES = {
    "searchindexer.exe": "Windows Search indexer",
    "explorer.exe": "Windows Explorer",
    "msmpeng.exe": "Antimalware Service Executable",
    "dwm.exe": "Desktop Window Manager",
    "svchost.exe": "Service Host",
    "memory compression": "Memory Compression",
    "system": "System",
}


def get_cpu_usage() -> ToolResult:
    """Current CPU utilization, sampled over one second."""

    def _impl() -> dict:
        usage = psutil.cpu_percent(interval=1)
        per_cpu = psutil.cpu_percent(interval=0, percpu=True)
        freq = None
        try:
            f = psutil.cpu_freq()
            freq = round(f.current, 0) if f else None
        except (OSError, NotImplementedError, AttributeError):
            freq = None
        load = None
        if hasattr(psutil, "getloadavg") and not IS_WINDOWS:
            try:
                load = [round(x, 2) for x in psutil.getloadavg()]
            except OSError:
                load = None
        return {
            "usage_percent": usage,
            "per_cpu_percent": per_cpu,
            "speed_mhz": freq,
            "logical_cpus": psutil.cpu_count(logical=True),
            "physical_cpus": psutil.cpu_count(logical=False),
            "sample_seconds": 1,
            "load_average": load,
        }

    return run_tool("get_cpu_usage", _impl)


def get_memory_usage() -> ToolResult:
    """Current physical memory and swap/page-file usage."""

    def _impl() -> dict:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "usage_percent": memory.percent,
            "total_gb": round(memory.total / _GB, 2),
            "available_gb": round(memory.available / _GB, 2),
            "used_gb": round((memory.total - memory.available) / _GB, 2),
            "swap_percent": swap.percent,
            "swap_total_gb": round(swap.total / _GB, 2),
        }

    return run_tool("get_memory_usage", _impl)


def get_memory_details() -> ToolResult:
    """Committed, cached and compressed memory (Task Manager's memory panel)."""

    def _impl() -> dict:
        vm = psutil.virtual_memory()
        data: dict = {
            "total_gb": round(vm.total / _GB, 2),
            "used_gb": round((vm.total - vm.available) / _GB, 2),
            "available_gb": round(vm.available / _GB, 2),
            "usage_percent": vm.percent,
            "committed_gb": None,
            "commit_limit_gb": None,
            "cached_gb": None,
            "compressed_mb": None,
        }
        perf = winapi.performance_info()
        if perf:
            data["committed_gb"] = round(perf["commit_total"] / _GB, 2)
            data["commit_limit_gb"] = round(perf["commit_limit"] / _GB, 2)
            data["cached_gb"] = round(perf["system_cache"] / _GB, 2)
            data["compressed_mb"] = _compressed_memory_mb()
        else:
            cached = getattr(vm, "cached", None)
            if cached is not None:
                data["cached_gb"] = round(cached / _GB, 2)
            committed = _linux_committed_bytes()
            if committed is not None:
                data["committed_gb"] = round(committed / _GB, 2)
                data["commit_limit_gb"] = round(
                    (vm.total + psutil.swap_memory().total) / _GB, 2)
        return data

    return run_tool("get_memory_details", _impl)


def _compressed_memory_mb() -> float | None:
    """Working set of the 'Memory Compression' process, as Task Manager shows.

    Optional detail: any failure yields None rather than failing the tool.
    """
    try:
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() in ("memory compression",
                                                         "memcompression"):
                return round(proc.memory_info().rss / _MB, 0)
    except (psutil.Error, OSError):
        return None
    return None


def _linux_committed_bytes() -> int | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("Committed_AS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def get_disk_activity() -> ToolResult:
    """Disk read/write throughput and active time, sampled over one second."""

    def _impl() -> dict:
        first = psutil.disk_io_counters()
        start = time.perf_counter()
        time.sleep(1.0)
        second = psutil.disk_io_counters()
        elapsed = time.perf_counter() - start
        if first is None or second is None:
            return {"available": False}
        read = (second.read_bytes - first.read_bytes) / elapsed
        write = (second.write_bytes - first.write_bytes) / elapsed
        busy_ms = None
        if hasattr(second, "busy_time"):
            busy_ms = second.busy_time - first.busy_time
        elif hasattr(second, "read_time"):
            busy_ms = (second.read_time - first.read_time) + (
                second.write_time - first.write_time)
        active = None
        if busy_ms is not None:
            active = round(min(100.0, max(0.0, busy_ms / (elapsed * 1000) * 100)), 1)
        return {
            "available": True,
            "read_mb_s": round(read / _MB, 2),
            "write_mb_s": round(write / _MB, 2),
            "active_time_percent": active,
        }

    return run_tool("get_disk_activity", _impl)


# --- processes -------------------------------------------------------------
def _display_name(name: str, exe: str | None) -> str:
    known = _KNOWN_NAMES.get(name.lower())
    if known:
        return known
    if exe:
        description = winapi.file_description(exe)
        if description:
            return description
    stem = Path(name).stem if name.lower().endswith(".exe") else name
    return stem[:1].upper() + stem[1:]


def _snapshot() -> tuple[list[dict], set[int]]:
    """Sample every process once, with CPU normalized across all cores."""
    cores = psutil.cpu_count(logical=True) or 1
    tracked = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc.cpu_percent(None)
            tracked.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.5)
    hung = winapi.hung_window_pids()

    procs: list[dict] = []
    for proc in tracked:
        try:
            with proc.oneshot():
                name = proc.info.get("name") or "?"
                mem = proc.memory_info().rss
                cpu = proc.cpu_percent(None) / cores
                try:
                    exe = proc.exe() if IS_WINDOWS else None
                except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
                    exe = None
            procs.append({
                "pid": proc.pid,
                "name": name,
                "exe": exe,
                "cpu_percent": round(cpu, 1),
                "memory_mb": round(mem / _MB, 1),
                "not_responding": proc.pid in hung,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return procs, hung


def _group(procs: list[dict]) -> list[dict]:
    """Group processes by executable name, like Task Manager's app rows."""
    groups: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "memory_mb": 0.0, "cpu_percent": 0.0,
        "not_responding": False, "pids": [], "exe": None,
    })
    for p in procs:
        g = groups[p["name"].lower()]
        g["name"] = p["name"]
        g["count"] += 1
        g["memory_mb"] += p["memory_mb"]
        g["cpu_percent"] += p["cpu_percent"]
        g["not_responding"] = g["not_responding"] or p["not_responding"]
        g["pids"].append(p["pid"])
        g["exe"] = g["exe"] or p.get("exe")
    result = []
    for g in groups.values():
        result.append({
            "name": g["name"],
            "display_name": _display_name(g["name"], g["exe"]),
            "count": g["count"],
            "memory_mb": round(g["memory_mb"], 1),
            "cpu_percent": round(g["cpu_percent"], 1),
            "not_responding": g["not_responding"],
            "pids": g["pids"][:32],
        })
    return sorted(result, key=lambda g: g["memory_mb"], reverse=True)


def get_running_processes() -> ToolResult:
    """Running processes, grouped by app, with memory, CPU and responsiveness."""

    def _impl() -> dict:
        procs, hung = _snapshot()
        groups = _group(procs)
        for p in procs:
            p.pop("exe", None)
        return {
            "process_count": len(procs),
            "app_count": len(groups),
            "not_responding_count": sum(1 for g in groups if g["not_responding"]),
            "groups": groups[:40],
            "processes": sorted(procs, key=lambda p: p["memory_mb"], reverse=True)[:50],
        }

    return run_tool("get_running_processes", _impl)


def get_top_cpu_processes(limit: int = 5) -> ToolResult:
    """Top apps by CPU usage (normalized to total CPU capacity)."""

    def _impl() -> dict:
        procs, _ = _snapshot()
        groups = sorted(_group(procs), key=lambda g: g["cpu_percent"], reverse=True)
        top = sorted(procs, key=lambda p: p["cpu_percent"], reverse=True)[:limit]
        for p in top:
            p.pop("exe", None)
        return {"limit": limit, "top_cpu_processes": top, "top_cpu_apps": groups[:limit]}

    return run_tool("get_top_cpu_processes", _impl)


def get_top_memory_processes(limit: int = 5) -> ToolResult:
    """Top apps by memory usage."""

    def _impl() -> dict:
        procs, _ = _snapshot()
        groups = _group(procs)
        top = sorted(procs, key=lambda p: p["memory_mb"], reverse=True)[:limit]
        for p in top:
            p.pop("exe", None)
        return {"limit": limit, "top_memory_processes": top,
                "top_memory_apps": groups[:limit]}

    return run_tool("get_top_memory_processes", _impl)


def get_unresponsive_apps() -> ToolResult:
    """Apps with a window Windows reports as 'Not responding'."""

    def _impl() -> dict:
        hung = winapi.hung_window_pids()
        apps = []
        for pid in sorted(hung):
            try:
                proc = psutil.Process(pid)
                apps.append({"pid": pid, "name": proc.name(),
                             "memory_mb": round(proc.memory_info().rss / _MB, 1)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {"supported": IS_WINDOWS, "count": len(apps), "apps": apps}

    return run_tool("get_unresponsive_apps", _impl)


def cpu_count() -> int:
    return os.cpu_count() or 1
