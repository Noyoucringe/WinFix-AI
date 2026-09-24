"""Application crash diagnostics (read-only)."""

from __future__ import annotations

import re

from app.core.platform_utils import IS_WINDOWS, run_powershell_json
from app.core.result import ToolResult, run_tool, unsupported_result

# Event 1000 ("Application Error") messages start with this English-invariant
# field order; the app name is the first comma-separated value after the colon.
_APP_NAME = re.compile(r":\s*([^,\s]+\.exe)", re.IGNORECASE)


def get_recent_application_crashes() -> ToolResult:
    """Application crashes (Windows Error Reporting, event 1000) in the last 7 days."""
    if not IS_WINDOWS:
        return unsupported_result("get_recent_application_crashes",
                                  "Crash logs require Windows")

    def _impl() -> dict:
        rows = run_powershell_json(
            "Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000;"
            "StartTime=(Get-Date).AddDays(-7)} -MaxEvents 30 -ErrorAction SilentlyContinue |"
            " Select-Object @{n='Time';e={$_.TimeCreated.ToString('o')}},"
            "@{n='Message';e={if($_.Message){$_.Message.Split([char]10)[0]}}}"
            " | ConvertTo-Json -Compress",
            timeout=30,
        )
        apps: dict[str, int] = {}
        for r in rows:
            match = _APP_NAME.search(r.get("Message") or "")
            name = match.group(1) if match else "Unknown app"
            apps[name] = apps.get(name, 0) + 1
        top = sorted(apps.items(), key=lambda kv: kv[1], reverse=True)
        return {"count": len(rows), "days": 7,
                "apps": [{"name": n, "crashes": c} for n, c in top[:10]]}

    return run_tool("get_recent_application_crashes", _impl)
