"""Application remediation actions (whitelisted)."""

from __future__ import annotations

from app.core.result import ToolResult
from app.remediation._common import windows_action

# Never terminate these, even if requested.
_PROTECTED = {
    "system", "system idle process", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "smss.exe", "svchost.exe",
}


def terminate_unresponsive_application(pid: int) -> ToolResult:
    """Terminate a specific process by PID.

    Refuses to terminate protected system processes. Requires the PID to
    exist. This is a targeted action — it never scans-and-kills broadly.
    """

    def _impl() -> dict:
        import psutil

        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess as exc:
            raise ValueError(f"No process with PID {pid}") from exc

        name = (proc.name() or "").lower()
        if name in _PROTECTED:
            raise ValueError(f"Refusing to terminate protected process '{name}'")

        proc.terminate()
        try:
            proc.wait(timeout=5)
            terminated = True
        except psutil.TimeoutExpired:
            proc.kill()
            terminated = True

        return {
            "action": "terminate_unresponsive_application",
            "pid": pid,
            "name": name,
            "terminated": terminated,
        }

    return windows_action("terminate_unresponsive_application", _impl)
