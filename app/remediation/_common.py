"""Shared helpers for remediation actions."""

from __future__ import annotations

from typing import Callable

from app.core.logging_setup import get_logger
from app.core.platform_utils import IS_WINDOWS, run_powershell
from app.core.result import ToolResult, run_tool, unsupported_result

logger = get_logger("remediation")

# The only services any remediation may restart. Service names are inserted
# into PowerShell scripts, so they must come from this constant set — never
# from the user or an LLM.
RESTARTABLE_SERVICES = frozenset({
    "wuauserv", "bits", "WSearch", "Spooler", "Audiosrv", "bthserv", "WlanSvc",
})


class PreconditionError(Exception):
    """A remediation's safety precondition was not met; nothing was changed."""


def windows_action(tool: str, impl: Callable[[], dict]) -> ToolResult:
    """Run a Windows-only remediation, degrading gracefully elsewhere."""
    if not IS_WINDOWS:
        return unsupported_result(tool, "This fix can only be applied on Windows")
    logger.info("applying remediation",
                extra={"component": "remediation", "event": "apply", "tool": tool})
    result = run_tool(tool, impl)
    logger.info("remediation finished",
                extra={"component": "remediation", "event": "done", "tool": tool,
                       "status": "ok" if result.get("success") else "fail",
                       "duration_ms": result.get("duration_ms")})
    return result


def restart_service(name: str, timeout: float = 90.0) -> dict:
    """Restart (or start, if stopped) one allow-listed Windows service.

    ``Restart-Service -Force`` also restarts dependent services and never asks
    for interactive confirmation, unlike ``net stop``.
    """
    if name not in RESTARTABLE_SERVICES:
        raise PreconditionError(f"Service '{name}' is not on the restart allow-list")
    out = run_powershell(
        f"Restart-Service -Name '{name}' -Force -ErrorAction Stop;"
        f"(Get-Service -Name '{name}').Status.ToString()",
        timeout=timeout,
    )
    status = (out.strip().splitlines() or ["Unknown"])[-1].strip()
    return {"service": name, "status_after": status, "restarted": True}
