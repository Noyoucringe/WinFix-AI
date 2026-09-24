"""Service remediation actions (whitelisted)."""

from __future__ import annotations

from app.core.result import ToolResult
from app.remediation._common import restart_service, windows_action


def restart_windows_update_service() -> ToolResult:
    """Restart the Windows Update service (wuauserv)."""
    return windows_action("restart_windows_update_service",
                          lambda: restart_service("wuauserv"))


def restart_print_spooler() -> ToolResult:
    """Restart the Print Spooler service (Spooler)."""
    return windows_action("restart_print_spooler", lambda: restart_service("Spooler"))


def restart_windows_search() -> ToolResult:
    """Restart the Windows Search service (WSearch)."""
    return windows_action("restart_windows_search", lambda: restart_service("WSearch"))


def restart_bluetooth_service() -> ToolResult:
    """Restart the Bluetooth Support Service (bthserv)."""
    return windows_action("restart_bluetooth_service",
                          lambda: restart_service("bthserv"))


def restart_bits_service() -> ToolResult:
    """Restart the Background Intelligent Transfer Service (bits)."""
    return windows_action("restart_bits_service", lambda: restart_service("bits"))


def restart_wlan_service() -> ToolResult:
    """Restart the WLAN AutoConfig service (WlanSvc)."""
    return windows_action("restart_wlan_service", lambda: restart_service("WlanSvc"))
