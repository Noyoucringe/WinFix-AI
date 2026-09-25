"""Live performance sampling for the Diagnostics page (read-only).

Unlike the one-shot diagnostic tools, the sampler is called repeatedly (every
2 seconds) and computes rates from the previous call instead of sleeping:
CPU %, a rolling 30-second CPU average, disk throughput/active time and
per-process CPU.
"""

from __future__ import annotations

import time
from collections import deque

import psutil

from app.core import winapi
from app.diagnostics.performance import _compressed_memory_mb, _group, iter_processes
from app.diagnostics.storage import SYSTEM_DRIVE, _drive_label

_GB = 1024 ** 3
_MB = 1024 ** 2


class LiveSampler:
    def __init__(self, interval_s: float = 2.0) -> None:
        self._cpu = deque(maxlen=max(1, round(30 / interval_s)))
        self._procs: dict[int, psutil.Process] = {}
        self._io = None
        self._io_time = 0.0
        self._ticks = 0
        self._compressed: float | None = None
        psutil.cpu_percent(None)

    def sample(self) -> dict:
        self._ticks += 1
        return {"cpu": self._cpu_sample(), "memory": self._memory(), "disk": self._disk(),
                "processes": self._processes(), "uptime_s": time.time() - psutil.boot_time()}

    def _cpu_sample(self) -> dict:
        usage = psutil.cpu_percent(None)
        self._cpu.append(usage)
        try:
            freq = psutil.cpu_freq()
            speed = round(freq.current / 1000, 2) if freq and freq.current else None
        except (OSError, NotImplementedError, AttributeError):
            speed = None
        return {"usage_percent": usage, "average_percent": sum(self._cpu) / len(self._cpu),
                "average_window_s": len(self._cpu) * 2, "speed_ghz": speed}

    def _memory(self) -> dict:
        vm = psutil.virtual_memory()
        data = {"usage_percent": vm.percent, "total_gb": vm.total / _GB,
                "used_gb": (vm.total - vm.available) / _GB, "available_gb": vm.available / _GB,
                "committed_gb": None, "commit_limit_gb": None, "cached_gb": None,
                "compressed_mb": None}
        perf = winapi.performance_info()
        if perf:
            data.update(committed_gb=perf["commit_total"] / _GB,
                        commit_limit_gb=perf["commit_limit"] / _GB,
                        cached_gb=perf["system_cache"] / _GB)
            if self._ticks % 5 == 1:  # expensive: look up every 10 seconds
                self._compressed = _compressed_memory_mb()
            data["compressed_mb"] = self._compressed
        elif getattr(vm, "cached", None) is not None:
            data["cached_gb"] = vm.cached / _GB
        return data

    def _disk(self) -> dict:
        usage = psutil.disk_usage(SYSTEM_DRIVE)
        data = {"drive": _drive_label(), "usage_percent": usage.percent,
                "free_gb": usage.free / _GB, "total_gb": usage.total / _GB,
                "read_mb_s": None, "write_mb_s": None, "active_percent": None}
        now = time.perf_counter()
        io = psutil.disk_io_counters()
        if io is not None and self._io is not None:
            elapsed = max(0.001, now - self._io_time)
            data["read_mb_s"] = (io.read_bytes - self._io.read_bytes) / elapsed / _MB
            data["write_mb_s"] = (io.write_bytes - self._io.write_bytes) / elapsed / _MB
            if hasattr(io, "busy_time"):
                busy = io.busy_time - self._io.busy_time
            else:
                busy = (io.read_time - self._io.read_time) + (io.write_time - self._io.write_time)
            data["active_percent"] = min(100.0, max(0.0, busy / (elapsed * 1000) * 100))
        self._io, self._io_time = io, now
        return data

    def _processes(self) -> dict:
        cores = psutil.cpu_count(logical=True) or 1
        hung = winapi.hung_window_pids()
        seen, rows = set(), []
        for proc in iter_processes():
            pid = proc.info["pid"]
            seen.add(pid)
            cached = self._procs.setdefault(pid, proc)
            try:
                with cached.oneshot():
                    try:
                        exe = cached.exe()
                    except (psutil.AccessDenied, OSError):
                        exe = None
                    rows.append({"pid": pid, "name": proc.info.get("name") or "?", "exe": exe,
                                 "cpu_percent": cached.cpu_percent(None) / cores,
                                 "memory_mb": cached.memory_info().rss / _MB,
                                 "not_responding": pid in hung})
            except (psutil.Error, OSError):
                continue
        for pid in list(self._procs):
            if pid not in seen:
                del self._procs[pid]
        groups = _group(rows)
        return {"count": len(rows), "groups": groups[:12]}
