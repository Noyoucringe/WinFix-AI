"""Storage remediation actions (whitelisted).

These only ever touch well-known temporary locations. They never delete user
documents and never accept an arbitrary path.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.core.platform_utils import run_command
from app.core.result import ToolResult
from app.remediation._common import windows_action


def _clear_dir(path: Path) -> dict:
    removed = 0
    freed_bytes = 0
    errors = 0
    if not path.exists():
        return {"path": str(path), "removed": 0, "freed_mb": 0.0, "errors": 0}
    for entry in path.iterdir():
        try:
            if entry.is_file() or entry.is_symlink():
                size = entry.stat().st_size
                entry.unlink()
                removed += 1
                freed_bytes += size
            elif entry.is_dir():
                size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
                freed_bytes += size
        except (PermissionError, OSError):
            errors += 1
    return {
        "path": str(path),
        "removed": removed,
        "freed_mb": round(freed_bytes / (1024 ** 2), 1),
        "errors": errors,
    }


def clear_safe_temp_files() -> ToolResult:
    """Clear the user and system TEMP directories of removable files."""

    def _impl() -> dict:
        targets = []
        user_temp = os.environ.get("TEMP")
        if user_temp:
            targets.append(Path(user_temp))
        windir = os.environ.get("WINDIR", r"C:\Windows")
        targets.append(Path(windir) / "Temp")

        results = [_clear_dir(p) for p in targets]
        total_freed = round(sum(r["freed_mb"] for r in results), 1)
        return {
            "action": "clear_safe_temp_files",
            "total_freed_mb": total_freed,
            "locations": results,
        }

    return windows_action("clear_safe_temp_files", _impl)


def clear_windows_update_cache_if_safe() -> ToolResult:
    """Clear the Windows Update download cache after stopping the services.

    Only clears ``SoftwareDistribution\\Download``; restarts the services after.
    """

    def _impl() -> dict:
        # Stop update services so the cache is not in use.
        for svc in ("wuauserv", "bits"):
            try:
                run_command(["net", "stop", svc], timeout=30)
            except Exception:  # noqa: BLE001
                pass

        windir = os.environ.get("WINDIR", r"C:\Windows")
        cache = Path(windir) / "SoftwareDistribution" / "Download"
        cleared = _clear_dir(cache)

        for svc in ("wuauserv", "bits"):
            try:
                run_command(["net", "start", svc], timeout=30)
            except Exception:  # noqa: BLE001
                pass

        return {"action": "clear_windows_update_cache_if_safe", "cache": cleared}

    return windows_action("clear_windows_update_cache_if_safe", _impl)


def empty_recycle_bin() -> ToolResult:
    """Empty the Recycle Bin via PowerShell (``Clear-RecycleBin``)."""

    def _impl() -> dict:
        from app.core.platform_utils import run_powershell

        run_powershell("Clear-RecycleBin -Force -ErrorAction SilentlyContinue")
        return {"action": "empty_recycle_bin", "emptied": True}

    return windows_action("empty_recycle_bin", _impl)
