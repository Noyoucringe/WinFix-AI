"""Graphics / GPU diagnostics (read-only).

* ``get_gpu_info``: graphics adapters, their driver version and age, and the
  Device Manager status (Win32_VideoController).
* ``get_gpu_usage``: how busy each GPU engine is and which apps use it, from
  the locale-independent WMI performance classes behind Task Manager's GPU
  column (Win32_PerfFormattedData_GPUPerformanceCounters_*).
* ``get_display_driver_errors``: display driver crashes and resets (TDR) in
  the System log over the last 7 days.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import psutil

from app.core.platform_utils import IS_WINDOWS, run_powershell_json
from app.core.result import ToolResult, run_tool, unsupported_result

_MB = 1024 ** 2
_ENGINE = re.compile(r"pid_(\d+)_.*engtype_([A-Za-z0-9]+)", re.IGNORECASE)
_BASIC_ADAPTER = ("microsoft basic display", "microsoft basic render")
# Providers that log display driver problems. 4101 = "Display driver stopped
# responding and has successfully recovered" (a TDR).
_DISPLAY_PROVIDERS = ("Display", "nvlddmkm", "amdkmdag", "amdkmdap", "amdwddmg",
                      "igfx", "igfxn", "Microsoft-Windows-DxgKrnl")


def _driver_age_days(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return (date.today() - datetime.strptime(value[:10], "%Y-%m-%d").date()).days
    except ValueError:
        return None


def get_gpu_info() -> ToolResult:
    """Graphics adapters, driver versions and dates, and device status."""
    if not IS_WINDOWS:
        return unsupported_result("get_gpu_info", "Graphics adapter details require Windows")

    def _impl() -> dict:
        rows = run_powershell_json(
            "Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | "
            "Select-Object Name,DriverVersion,"
            "@{n='DriverDate';e={if($_.DriverDate){$_.DriverDate.ToString('yyyy-MM-dd')}}},"
            "Status,ConfigManagerErrorCode,CurrentHorizontalResolution,"
            "CurrentVerticalResolution,CurrentRefreshRate,VideoProcessor | "
            "ConvertTo-Json -Compress", timeout=25)
        adapters = []
        for r in rows:
            name = (r.get("Name") or "Unknown graphics adapter").strip()
            code = r.get("ConfigManagerErrorCode") or 0
            width, height = r.get("CurrentHorizontalResolution"), r.get("CurrentVerticalResolution")
            adapters.append({
                "name": name,
                "driver_version": r.get("DriverVersion"),
                "driver_date": r.get("DriverDate"),
                "driver_age_days": _driver_age_days(r.get("DriverDate")),
                "status": r.get("Status"),
                "problem_code": code,
                "healthy": (r.get("Status") in (None, "OK")) and not code,
                "basic_driver": name.lower().startswith(_BASIC_ADAPTER),
                "resolution": f"{width} x {height}" if width and height else None,
                "refresh_rate": r.get("CurrentRefreshRate"),
            })
        return {"count": len(adapters), "adapters": adapters,
                "problems": [a["name"] for a in adapters if not a["healthy"]]}

    return run_tool("get_gpu_info", _impl)


def get_gpu_usage() -> ToolResult:
    """GPU engine utilization overall and per app, plus dedicated GPU memory."""
    if not IS_WINDOWS:
        return unsupported_result("get_gpu_usage", "GPU performance counters require Windows")

    def _impl() -> dict:
        # Formatted counters need two reads; the first primes the provider.
        engines = run_powershell_json(
            "$c='Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine';"
            "$null=Get-CimInstance $c -ErrorAction SilentlyContinue;Start-Sleep -Milliseconds 600;"
            "Get-CimInstance $c -ErrorAction SilentlyContinue | "
            "Where-Object { $_.UtilizationPercentage -gt 0 } | "
            "Select-Object Name,UtilizationPercentage | ConvertTo-Json -Compress", timeout=25)
        memory = run_powershell_json(
            "Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory "
            "-ErrorAction SilentlyContinue | Where-Object { $_.DedicatedUsage -gt 0 } | "
            "Select-Object Name,DedicatedUsage | ConvertTo-Json -Compress", timeout=25)

        by_engine: dict[str, float] = {}
        by_pid: dict[int, float] = {}
        for row in engines:
            match = _ENGINE.search(row.get("Name") or "")
            if not match:
                continue
            pid, engine = int(match.group(1)), match.group(2)
            value = float(row.get("UtilizationPercentage") or 0)
            by_engine[engine] = by_engine.get(engine, 0.0) + value
            by_pid[pid] = max(by_pid.get(pid, 0.0), value)
        mem_by_pid: dict[int, float] = {}
        for row in memory:
            match = re.search(r"pid_(\d+)_", row.get("Name") or "")
            if match:
                pid = int(match.group(1))
                mem_by_pid[pid] = mem_by_pid.get(pid, 0.0) + float(row.get("DedicatedUsage") or 0)

        apps: dict[str, dict] = {}
        for pid in set(by_pid) | set(mem_by_pid):
            try:
                name = psutil.Process(pid).name()
            except (psutil.Error, OSError):
                continue
            app = apps.setdefault(name.lower(), {"name": name, "gpu_percent": 0.0,
                                                 "gpu_memory_mb": 0.0, "count": 0})
            app["gpu_percent"] = min(100.0, app["gpu_percent"] + by_pid.get(pid, 0.0))
            app["gpu_memory_mb"] += mem_by_pid.get(pid, 0.0) / _MB
            app["count"] += 1
        top = sorted(apps.values(), key=lambda a: (a["gpu_percent"], a["gpu_memory_mb"]),
                     reverse=True)
        for app in top:
            app["gpu_percent"] = round(app["gpu_percent"], 1)
            app["gpu_memory_mb"] = round(app["gpu_memory_mb"], 1)
        engines_pct = {k: round(min(100.0, v), 1) for k, v in by_engine.items()}
        return {
            "utilization_percent": max(engines_pct.values(), default=0.0),
            "engines": engines_pct,
            "top_apps": top[:5],
            "dedicated_memory_used_mb": round(sum(mem_by_pid.values()) / _MB, 1),
        }

    return run_tool("get_gpu_usage", _impl)


def get_display_driver_errors() -> ToolResult:
    """Display driver crashes and recoveries (TDR) in the last 7 days."""
    if not IS_WINDOWS:
        return unsupported_result("get_display_driver_errors",
                                  "The Windows Event Log requires Windows")

    def _impl() -> dict:
        providers = ",".join(f"'{p}'" for p in _DISPLAY_PROVIDERS)  # constants only
        rows = run_powershell_json(
            f"Get-WinEvent -FilterHashtable @{{LogName='System';ProviderName={providers};"
            "Level=1,2,3;StartTime=(Get-Date).AddDays(-7)} -MaxEvents 50 "
            "-ErrorAction SilentlyContinue | Select-Object "
            "@{n='Time';e={$_.TimeCreated.ToString('o')}},Id,ProviderName,"
            "@{n='Message';e={if($_.Message){$_.Message.Split([char]10)[0]}}} | "
            "ConvertTo-Json -Compress", timeout=30)
        events = [{"time": r.get("Time"), "id": r.get("Id"), "source": r.get("ProviderName"),
                   "message": (r.get("Message") or "").strip()[:240]} for r in rows]
        resets = [e for e in events if e["id"] == 4101 or
                  (e["source"] or "").lower() in ("nvlddmkm", "amdkmdag", "amdkmdap")]
        return {"days": 7, "count": len(events), "driver_resets": len(resets),
                "last": events[0] if events else None, "events": events[:10]}

    return run_tool("get_display_driver_errors", _impl)
