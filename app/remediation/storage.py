"""Storage remediation actions (whitelisted).

These only ever touch Windows' own temporary locations and the Recycle Bin.
They never accept a path, and never touch documents or app data.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import time
from pathlib import Path

import psutil

from app.core.platform_utils import run_powershell
from app.core.result import ToolResult
from app.diagnostics.storage import temp_locations
from app.remediation._common import PreconditionError, windows_action

_MB = 1024 ** 2
# Skip anything modified in the last day: it may belong to a running installer
# or an app that is still open.
MIN_AGE_SECONDS = 24 * 3600


def _clear_dir(path: Path, min_age_s: float = MIN_AGE_SECONDS) -> dict:
    removed = skipped = errors = 0
    freed = 0
    cutoff = time.time() - min_age_s
    if not path.is_dir():
        return {"path": str(path), "removed": 0, "freed_mb": 0.0,
                "skipped_recent": 0, "errors": 0}
    for entry in path.iterdir():
        try:
            if entry.is_symlink():
                continue
            stat = entry.stat()
            if stat.st_mtime > cutoff:
                skipped += 1
                continue
            if entry.is_dir():
                size = sum(f.stat().st_size for f in entry.rglob("*")
                           if f.is_file() and not f.is_symlink())
                shutil.rmtree(entry)
            else:
                size = stat.st_size
                entry.unlink()
            removed += 1
            freed += size
        except OSError:
            # In use or protected — leave it alone.
            errors += 1
    return {"path": str(path), "removed": removed, "freed_mb": round(freed / _MB, 1),
            "skipped_recent": skipped, "errors": errors}


def clear_safe_temp_files() -> ToolResult:
    """Delete temporary files older than a day from the user and Windows TEMP folders."""

    def _impl() -> dict:
        results = [_clear_dir(p) for p in temp_locations()]
        return {"action": "clear_safe_temp_files",
                "freed_mb": round(sum(r["freed_mb"] for r in results), 1),
                "locations": results}

    return windows_action("clear_safe_temp_files", _impl)


def _updates_installing() -> bool:
    return any((p.info.get("name") or "").lower() == "tiworker.exe"
               for p in psutil.process_iter(["name"]))


def clear_windows_update_cache_if_safe() -> ToolResult:
    """Clear Windows Update's download cache, but never while updates install."""

    def _impl() -> dict:
        if _updates_installing():
            raise PreconditionError(
                "Windows is installing updates right now. Try again when it finishes.")
        cache = Path(os.environ.get("WINDIR", r"C:\Windows")) / "SoftwareDistribution" / "Download"
        run_powershell("Stop-Service -Name wuauserv,bits -Force -ErrorAction Stop", timeout=90)
        try:
            cleared = _clear_dir(cache, min_age_s=0)
        finally:
            run_powershell("Start-Service -Name wuauserv,bits -ErrorAction SilentlyContinue",
                           timeout=90)
        return {"action": "clear_windows_update_cache_if_safe", "cache": cleared,
                "freed_mb": cleared["freed_mb"]}

    return windows_action("clear_windows_update_cache_if_safe", _impl)


def empty_recycle_bin() -> ToolResult:
    """Permanently delete the items in the Recycle Bin (SHEmptyRecycleBinW)."""

    def _impl() -> dict:
        from app.core import winapi

        before = winapi.recycle_bin_usage() or (0, 0)
        sherb_noconfirmation, sherb_noprogressui, sherb_nosound = 0x1, 0x2, 0x4
        hr = ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, sherb_noconfirmation | sherb_noprogressui | sherb_nosound)
        # S_OK, or E_UNEXPECTED when the bin was already empty.
        if hr not in (0, -2147418113):
            raise OSError(f"SHEmptyRecycleBinW failed (HRESULT {hr & 0xFFFFFFFF:#010x})")
        return {"action": "empty_recycle_bin", "items_removed": before[1],
                "freed_mb": round(before[0] / _MB, 1)}

    return windows_action("empty_recycle_bin", _impl)
