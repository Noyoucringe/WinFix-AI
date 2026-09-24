"""Network remediation actions (whitelisted)."""

from __future__ import annotations

from app.core.platform_utils import run_command
from app.core.result import ToolResult
from app.remediation._common import windows_action


def flush_dns() -> ToolResult:
    """Flush the DNS resolver cache (``ipconfig /flushdns``)."""

    def _impl() -> dict:
        out = run_command(["ipconfig", "/flushdns"], timeout=15)
        return {"action": "flush_dns", "output_tail": out.strip().splitlines()[-1:]}

    return windows_action("flush_dns", _impl)


def renew_ip_configuration() -> ToolResult:
    """Renew the DHCP lease (``ipconfig /renew``)."""

    def _impl() -> dict:
        out = run_command(["ipconfig", "/renew"], timeout=45)
        return {"action": "renew_ip", "output_tail": out.strip().splitlines()[-3:]}

    return windows_action("renew_ip_configuration", _impl)


def release_ip_configuration() -> ToolResult:
    """Release the current DHCP lease (``ipconfig /release``)."""

    def _impl() -> dict:
        out = run_command(["ipconfig", "/release"], timeout=45)
        return {"action": "release_ip", "output_tail": out.strip().splitlines()[-3:]}

    return windows_action("release_ip_configuration", _impl)


def restart_network_adapter(adapter_name: str) -> ToolResult:
    """Disable then re-enable a named network adapter (requires admin)."""

    def _impl() -> dict:
        run_command(
            ["netsh", "interface", "set", "interface", adapter_name, "admin=disabled"],
            timeout=30,
        )
        run_command(
            ["netsh", "interface", "set", "interface", adapter_name, "admin=enabled"],
            timeout=30,
        )
        return {"action": "restart_adapter", "adapter": adapter_name, "restarted": True}

    return windows_action("restart_network_adapter", _impl)


def reset_winsock() -> ToolResult:
    """Reset the Winsock catalog (``netsh winsock reset``). Reboot recommended."""

    def _impl() -> dict:
        out = run_command(["netsh", "winsock", "reset"], timeout=30)
        return {
            "action": "reset_winsock",
            "reboot_recommended": True,
            "output_tail": out.strip().splitlines()[-2:],
        }

    return windows_action("reset_winsock", _impl)
