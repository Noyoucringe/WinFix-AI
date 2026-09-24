"""Network remediation actions (whitelisted)."""

from __future__ import annotations

import re

import psutil

from app.core.platform_utils import run_command
from app.core.result import ToolResult
from app.remediation._common import PreconditionError, windows_action

_SAFE_ADAPTER_NAME = re.compile(r"^[\w .()#\-]{1,64}$")


def validate_adapter_name(adapter_name: str) -> str:
    """Accept only the name of an adapter that actually exists on this PC."""
    if not _SAFE_ADAPTER_NAME.match(adapter_name or ""):
        raise PreconditionError("Adapter name contains unsupported characters")
    if adapter_name not in psutil.net_if_stats():
        raise PreconditionError(f"No network adapter named '{adapter_name}'")
    return adapter_name


def flush_dns() -> ToolResult:
    """Flush the DNS resolver cache (ipconfig /flushdns)."""

    def _impl() -> dict:
        run_command(["ipconfig", "/flushdns"], timeout=20)
        return {"action": "flush_dns", "flushed": True}

    return windows_action("flush_dns", _impl)


def renew_ip_configuration() -> ToolResult:
    """Renew the DHCP lease on all adapters (ipconfig /renew)."""

    def _impl() -> dict:
        run_command(["ipconfig", "/renew"], timeout=60)
        return {"action": "renew_ip_configuration", "renewed": True}

    return windows_action("renew_ip_configuration", _impl)


def release_ip_configuration() -> ToolResult:
    """Release the DHCP lease on all adapters (ipconfig /release)."""

    def _impl() -> dict:
        run_command(["ipconfig", "/release"], timeout=60)
        return {"action": "release_ip_configuration", "released": True}

    return windows_action("release_ip_configuration", _impl)


def restart_network_adapter(adapter_name: str) -> ToolResult:
    """Disable and re-enable one existing network adapter (requires admin)."""

    def _impl() -> dict:
        name = validate_adapter_name(adapter_name)
        # Passed as a single argv element — no shell, no string interpolation.
        run_command(["netsh", "interface", "set", "interface", f"name={name}",
                     "admin=disabled"], timeout=30)
        run_command(["netsh", "interface", "set", "interface", f"name={name}",
                     "admin=enabled"], timeout=30)
        return {"action": "restart_network_adapter", "adapter": name, "restarted": True}

    return windows_action("restart_network_adapter", _impl)


def reset_winsock() -> ToolResult:
    """Reset the Winsock catalog (netsh winsock reset). A restart is needed after."""

    def _impl() -> dict:
        run_command(["netsh", "winsock", "reset"], timeout=30)
        return {"action": "reset_winsock", "reboot_required": True}

    return windows_action("reset_winsock", _impl)
