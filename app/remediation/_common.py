"""Shared helpers for remediation actions."""

from __future__ import annotations

from typing import Callable

from app.core.logging_setup import get_logger
from app.core.platform_utils import IS_WINDOWS, run_command
from app.core.result import ToolResult, run_tool, unsupported_result

logger = get_logger("remediation")


def windows_action(tool: str, impl: Callable[[], dict]) -> ToolResult:
    """Run a Windows-only remediation, degrading gracefully off-Windows.

    Logs the change that was applied (never secrets).
    """
    if not IS_WINDOWS:
        return unsupported_result(tool, "Remediation requires Windows")
    logger.info(
        "applying remediation",
        extra={"component": "remediation", "event": "apply", "tool": tool},
    )
    result = run_tool(tool, impl)
    logger.info(
        "remediation finished",
        extra={
            "component": "remediation",
            "event": "done",
            "tool": tool,
            "status": "ok" if result.get("success") else "fail",
        },
    )
    return result


def restart_service(name: str, timeout: float = 30.0) -> dict:
    """Stop then start a Windows service using ``net`` (fixed argv, no shell)."""
    stop_out = ""
    try:
        stop_out = run_command(["net", "stop", name], timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - service may already be stopped
        stop_out = f"stop skipped: {exc}"
    start_out = run_command(["net", "start", name], timeout=timeout)
    return {
        "service": name,
        "restarted": True,
        "stop_output_tail": stop_out.strip().splitlines()[-1:],
        "start_output_tail": start_out.strip().splitlines()[-1:],
    }
