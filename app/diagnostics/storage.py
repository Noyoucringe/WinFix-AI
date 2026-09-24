"""Storage diagnostics: disk usage, partitions, free space, reclaimable space."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import psutil

from app.core import winapi
from app.core.platform_utils import IS_WINDOWS
from app.core.result import ToolResult, run_tool

_GB = 1024 ** 3
_MB = 1024 ** 2

SYSTEM_DRIVE = (os.environ.get("SystemDrive", "C:") + "\\") if IS_WINDOWS else "/"
LOW_SPACE_PERCENT = 90
LOW_SPACE_GB = 10


def _drive_label() -> str:
    return SYSTEM_DRIVE.rstrip("\\") or "/"


def get_disk_usage() -> ToolResult:
    """Disk usage for the system drive."""

    def _impl() -> dict:
        disk = psutil.disk_usage(SYSTEM_DRIVE)
        return {
            "drive": _drive_label(),
            "usage_percent": disk.percent,
            "total_gb": round(disk.total / _GB, 2),
            "used_gb": round(disk.used / _GB, 2),
            "free_gb": round(disk.free / _GB, 2),
        }

    return run_tool("get_disk_usage", _impl)


def get_disk_partitions() -> ToolResult:
    """Mounted partitions and their usage."""

    def _impl() -> dict:
        partitions = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            partitions.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gb": round(usage.total / _GB, 2),
                "free_gb": round(usage.free / _GB, 2),
                "usage_percent": usage.percent,
            })
        return {"partition_count": len(partitions), "partitions": partitions}

    return run_tool("get_disk_partitions", _impl)


def get_disk_free_space() -> ToolResult:
    """Free space on the system drive with a low-space flag."""

    def _impl() -> dict:
        disk = psutil.disk_usage(SYSTEM_DRIVE)
        free_gb = round(disk.free / _GB, 2)
        return {
            "drive": _drive_label(),
            "free_gb": free_gb,
            "total_gb": round(disk.total / _GB, 2),
            "usage_percent": disk.percent,
            "free_percent": round(100 - disk.percent, 1),
            "low_space": disk.percent >= LOW_SPACE_PERCENT or free_gb < LOW_SPACE_GB,
        }

    return run_tool("get_disk_free_space", _impl)


def _dir_size(path: Path, budget_s: float, max_files: int = 200_000) -> tuple[int, int, bool]:
    """(bytes, files, complete) — bounded so a huge folder can't stall a check."""
    total = files = 0
    deadline = time.monotonic() + budget_s
    stack = [path]
    while stack:
        if time.monotonic() > deadline or files >= max_files:
            return total, files, False
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, files, True


def temp_locations() -> list[Path]:
    """The only folders WinFix will ever clean: user and system TEMP."""
    locations = [Path(tempfile.gettempdir())]
    if IS_WINDOWS:
        locations.append(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Temp")
    seen, unique = set(), []
    for loc in locations:
        key = str(loc).lower()
        if key not in seen:
            seen.add(key)
            unique.append(loc)
    return unique


def get_reclaimable_space() -> ToolResult:
    """Space held by temporary files and the Recycle Bin (read-only sizing)."""

    def _impl() -> dict:
        locations = []
        temp_total = 0
        for loc in temp_locations():
            size, files, complete = _dir_size(loc, budget_s=6.0)
            temp_total += size
            locations.append({"path": str(loc), "size_mb": round(size / _MB, 1),
                              "files": files, "complete": complete})
        recycle = winapi.recycle_bin_usage()
        return {
            "temp_mb": round(temp_total / _MB, 1),
            "temp_locations": locations,
            "recycle_bin_mb": round(recycle[0] / _MB, 1) if recycle else None,
            "recycle_bin_items": recycle[1] if recycle else None,
        }

    return run_tool("get_reclaimable_space", _impl)
