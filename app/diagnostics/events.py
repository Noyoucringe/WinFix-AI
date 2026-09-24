"""Event log diagnostics (read-only). Reads the System and Application logs,
which standard (non-administrator) users are allowed to read."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS, run_powershell_json
from app.core.result import ToolResult, run_tool, unsupported_result

_MESSAGE_LIMIT = 300
# Numeric levels are locale-independent, unlike LevelDisplayName.
_LEVELS = {1: "Critical", 2: "Error"}


def _event_script(log_name: str, hours: int, max_events: int) -> str:
    # log_name is one of two constants below — never user input.
    return (
        f"Get-WinEvent -FilterHashtable @{{LogName='{log_name}';Level=1,2;"
        f"StartTime=(Get-Date).AddHours(-{int(hours)})}} -MaxEvents {int(max_events)}"
        " -ErrorAction SilentlyContinue | Select-Object "
        "@{n='Time';e={$_.TimeCreated.ToString('o')}},Id,"
        "Level,ProviderName,"
        "@{n='Message';e={if($_.Message){$_.Message.Split([char]10)[0]}}}"
        " | ConvertTo-Json -Compress"
    )


def _recent_events(log_name: str, tool: str, hours: int = 24) -> ToolResult:
    if not IS_WINDOWS:
        return unsupported_result(tool, "The Windows Event Log requires Windows")

    def _impl() -> dict:
        rows = run_powershell_json(_event_script(log_name, hours, 25), timeout=30)
        events = [{
            "time": r.get("Time"),
            "id": r.get("Id"),
            "level": _LEVELS.get(r.get("Level"), "Error"),
            "source": r.get("ProviderName"),
            "message": (r.get("Message") or "").strip()[:_MESSAGE_LIMIT],
        } for r in rows]
        sources: dict[str, int] = {}
        for e in events:
            sources[e["source"] or "Unknown"] = sources.get(e["source"] or "Unknown", 0) + 1
        top = sorted(sources.items(), key=lambda kv: kv[1], reverse=True)[:5]
        return {"log": log_name, "hours": hours, "count": len(events),
                "critical_count": sum(1 for e in events if e["level"] == "Critical"),
                "top_sources": [{"source": s, "count": c} for s, c in top],
                "events": events}

    return run_tool(tool, _impl)


def get_recent_system_errors() -> ToolResult:
    """Critical and error events in the System log over the last 24 hours."""
    return _recent_events("System", "get_recent_system_errors")


def get_recent_application_errors() -> ToolResult:
    """Critical and error events in the Application log over the last 24 hours."""
    return _recent_events("Application", "get_recent_application_errors")
