"""Storage diagnostics: disk usage, partitions, free space (read-only)."""

from __future__ import annotations

import psutil

from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool

SYSTEM_DRIVE = "C:\\" if IS_WINDOWS else "/"


def get_disk_usage() -> ToolResult:
    """Disk usage for the system drive."""

    def _impl() -> dict:
        disk = psutil.disk_usage(SYSTEM_DRIVE)
        return {
            "drive": SYSTEM_DRIVE.rstrip("\\") or "/",
            "usage_percent": disk.percent,
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "used_gb": round(disk.used / (1024 ** 3), 2),
            "free_gb": round(disk.free / (1024 ** 3), 2),
        }

    return run_tool("get_disk_usage", _impl)


def get_disk_partitions() -> ToolResult:
    """Enumerate mounted partitions and their usage."""

    def _impl() -> dict:
        partitions = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            partitions.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "usage_percent": usage.percent,
                }
            )
        return {"partition_count": len(partitions), "partitions": partitions}

    return run_tool("get_disk_partitions", _impl)


def get_disk_free_space() -> ToolResult:
    """Free space on the system drive with a low-space flag."""

    def _impl() -> dict:
        disk = psutil.disk_usage(SYSTEM_DRIVE)
        free_gb = round(disk.free / (1024 ** 3), 2)
        return {
            "drive": SYSTEM_DRIVE.rstrip("\\") or "/",
            "free_gb": free_gb,
            "free_percent": round(100 - disk.percent, 1),
            "low_space": disk.percent >= 90 or free_gb < 5,
        }

    return run_tool("get_disk_free_space", _impl)
