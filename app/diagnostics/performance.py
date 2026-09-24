"""Performance diagnostics: CPU, memory, and process inspection (read-only)."""

from __future__ import annotations

import psutil

from app.core.result import ToolResult, run_tool


def get_cpu_usage() -> ToolResult:
    """Current CPU utilization percentage."""

    def _impl() -> dict:
        usage = psutil.cpu_percent(interval=1)
        per_cpu = psutil.cpu_percent(interval=0, percpu=True)
        load = None
        if hasattr(psutil, "getloadavg"):
            try:
                load = [round(x, 2) for x in psutil.getloadavg()]
            except (OSError, AttributeError):
                load = None
        return {
            "usage_percent": usage,
            "per_cpu_percent": per_cpu,
            "load_average": load,
        }

    return run_tool("get_cpu_usage", _impl)


def get_memory_usage() -> ToolResult:
    """Current virtual memory usage."""

    def _impl() -> dict:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "usage_percent": memory.percent,
            "total_gb": round(memory.total / (1024 ** 3), 2),
            "available_gb": round(memory.available / (1024 ** 3), 2),
            "used_gb": round(memory.used / (1024 ** 3), 2),
            "swap_percent": swap.percent,
            "swap_total_gb": round(swap.total / (1024 ** 3), 2),
        }

    return run_tool("get_memory_usage", _impl)


def _iter_processes() -> list[dict]:
    procs: list[dict] = []
    # Prime cpu_percent measurement.
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    psutil.cpu_percent(interval=0.3)
    for proc in psutil.process_iter(["pid", "name", "memory_info", "username"]):
        try:
            info = proc.info
            mem = info.get("memory_info")
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info.get("name") or "?",
                    "cpu_percent": round(proc.cpu_percent(None), 1),
                    "memory_mb": round(mem.rss / (1024 ** 2), 1) if mem else 0.0,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return procs


def get_running_processes() -> ToolResult:
    """Count and list running processes (summarized)."""

    def _impl() -> dict:
        procs = _iter_processes()
        return {
            "process_count": len(procs),
            "processes": sorted(procs, key=lambda p: p["memory_mb"], reverse=True)[:50],
        }

    return run_tool("get_running_processes", _impl)


def get_top_cpu_processes(limit: int = 5) -> ToolResult:
    """Top processes by CPU usage."""

    def _impl() -> dict:
        procs = _iter_processes()
        top = sorted(procs, key=lambda p: p["cpu_percent"], reverse=True)[:limit]
        return {"limit": limit, "top_cpu_processes": top}

    return run_tool("get_top_cpu_processes", _impl)


def get_top_memory_processes(limit: int = 5) -> ToolResult:
    """Top processes by memory usage."""

    def _impl() -> dict:
        procs = _iter_processes()
        top = sorted(procs, key=lambda p: p["memory_mb"], reverse=True)[:limit]
        return {"limit": limit, "top_memory_processes": top}

    return run_tool("get_top_memory_processes", _impl)
