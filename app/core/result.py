"""The standard tool result contract used by every diagnostic and
remediation tool.

The canonical shape is a plain ``dict`` (preserving backwards compatibility
with the original diagnostics)::

    {
        "success": true,
        "tool": "get_cpu_usage",
        "data": {...} | None,
        "error": {"type": "...", "message": "..."} | None,
        "duration_ms": 142,
        "timestamp": "2026-09-24T...",
        "tool_version": "1.0"
    }

Helper builders make it easy to construct valid results and guarantee the
contract is respected.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

ToolResult = dict[str, Any]

DEFAULT_TOOL_VERSION = "1.0"

T = TypeVar("T")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def success_result(
    tool: str,
    data: dict[str, Any],
    *,
    duration_ms: float | None = None,
    tool_version: str = DEFAULT_TOOL_VERSION,
) -> ToolResult:
    """Build a successful tool result."""
    return {
        "success": True,
        "tool": tool,
        "data": data,
        "error": None,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "timestamp": _now_iso(),
        "tool_version": tool_version,
    }


def error_result(
    tool: str,
    error_type: str,
    message: str,
    *,
    duration_ms: float | None = None,
    tool_version: str = DEFAULT_TOOL_VERSION,
) -> ToolResult:
    """Build a failed tool result. A failed result never raises."""
    return {
        "success": False,
        "tool": tool,
        "data": None,
        "error": {"type": error_type, "message": message},
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "timestamp": _now_iso(),
        "tool_version": tool_version,
    }


def unsupported_result(tool: str, reason: str) -> ToolResult:
    """Result for a tool that cannot run on the current platform.

    Treated as a (non-crashing) failure so the engine keeps collecting other
    evidence. This is the graceful-degradation path when a Windows-only tool
    runs on a non-Windows host.
    """
    return error_result(tool, "UnsupportedPlatform", reason)


def run_tool(tool: str, fn: Callable[[], dict[str, Any]]) -> ToolResult:
    """Execute ``fn`` (which returns the ``data`` dict) and wrap it in the
    standard contract, timing it and turning any exception into an
    ``error_result``. Guarantees no exception escapes.
    """
    start = time.perf_counter()
    try:
        data = fn()
        duration_ms = (time.perf_counter() - start) * 1000
        return success_result(tool, data, duration_ms=duration_ms)
    except Exception as exc:  # noqa: BLE001 - deliberate: never crash the engine
        duration_ms = (time.perf_counter() - start) * 1000
        return error_result(
            tool, type(exc).__name__, str(exc), duration_ms=duration_ms
        )


def is_success(result: ToolResult) -> bool:
    return bool(result.get("success"))
