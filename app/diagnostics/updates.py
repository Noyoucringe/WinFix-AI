"""Windows Update diagnostics (read-only)."""

from __future__ import annotations

from app.core.platform_utils import IS_WINDOWS, run_powershell_json
from app.core.result import ToolResult, run_tool, unsupported_result

# Registry locations Windows uses to record that a restart is pending.
_REBOOT_KEYS = (
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
     "Windows Update"),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
     "Component servicing"),
)


def get_recent_updates() -> ToolResult:
    """Recently installed Windows updates."""
    if not IS_WINDOWS:
        return unsupported_result("get_recent_updates",
                                  "Windows Update history requires Windows")

    def _impl() -> dict:
        rows = run_powershell_json(
            "Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 10"
            " HotFixID,Description,@{n='InstalledOn';e={if($_.InstalledOn){"
            "$_.InstalledOn.ToString('yyyy-MM-dd')}}} | ConvertTo-Json -Compress",
            timeout=30,
        )
        updates = [{"id": r.get("HotFixID"), "description": r.get("Description"),
                    "installed_on": r.get("InstalledOn")} for r in rows]
        return {"count": len(updates), "updates": updates,
                "last_installed": updates[0]["installed_on"] if updates else None}

    return run_tool("get_recent_updates", _impl)


def get_pending_reboot() -> ToolResult:
    """Whether Windows is waiting for a restart to finish installing updates."""
    if not IS_WINDOWS:
        return unsupported_result("get_pending_reboot",
                                  "Pending-restart detection requires Windows")

    def _impl() -> dict:
        import winreg

        reasons = []
        for path, label in _REBOOT_KEYS:
            try:
                winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path))
                reasons.append(label)
            except OSError:
                continue
        # Many installers leave pending rename operations behind, so this is
        # reported separately and never on its own treated as "restart needed".
        file_ops = False
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Control\Session Manager") as key:
                value, _ = winreg.QueryValueEx(key, "PendingFileRenameOperations")
                file_ops = bool(value)
        except OSError:
            pass
        return {"reboot_pending": bool(reasons), "reasons": reasons,
                "file_operations_pending": file_ops}

    return run_tool("get_pending_reboot", _impl)
