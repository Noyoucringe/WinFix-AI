"""System remediation actions (whitelisted)."""

from __future__ import annotations

from app.core.platform_utils import run_command
from app.core.result import ToolResult
from app.remediation._common import restart_service, windows_action


def restart_explorer() -> ToolResult:
    """Restart Windows Explorer (the shell)."""

    def _impl() -> dict:
        try:
            run_command(["taskkill", "/f", "/im", "explorer.exe"], timeout=15)
        except Exception:  # noqa: BLE001 - may not be running
            pass
        # Explorer usually auto-restarts; start it explicitly to be sure.
        run_command(["cmd", "/c", "start", "explorer.exe"], timeout=15)
        return {"action": "restart_explorer", "restarted": True}

    return windows_action("restart_explorer", _impl)


def restart_audio_service() -> ToolResult:
    """Restart the Windows Audio service (``Audiosrv``)."""
    return windows_action("restart_audio_service", lambda: restart_service("Audiosrv"))
