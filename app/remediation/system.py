"""System remediation actions (whitelisted)."""

from __future__ import annotations

import os
import subprocess
import time

import psutil

from app.core.platform_utils import run_command
from app.core.result import ToolResult
from app.remediation._common import restart_service, windows_action


def restart_explorer() -> ToolResult:
    """Restart Windows Explorer (taskbar, Start and File Explorer windows)."""

    def _impl() -> dict:
        run_command(["taskkill", "/f", "/im", "explorer.exe"], timeout=15, check=False)
        time.sleep(1.5)
        # Windows usually relaunches the shell itself; start it if it didn't.
        if not any((p.info.get("name") or "").lower() == "explorer.exe"
                   for p in psutil.process_iter(["name"])):
            windir = os.environ.get("WINDIR", r"C:\Windows")
            subprocess.Popen(  # noqa: S603 - fixed path, no shell
                [os.path.join(windir, "explorer.exe")],
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
                close_fds=True,
            )
        return {"action": "restart_explorer", "restarted": True}

    return windows_action("restart_explorer", _impl)


def restart_audio_service() -> ToolResult:
    """Restart the Windows Audio service (Audiosrv)."""
    return windows_action("restart_audio_service", lambda: restart_service("Audiosrv"))
