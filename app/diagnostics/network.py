"""Network diagnostics (read-only).

psutil-based adapter/IP inspection works cross-platform. Connectivity checks
(ping, DNS, internet) use standard sockets and the system ``ping`` binary with
fixed, platform-appropriate arguments.
"""

from __future__ import annotations

import socket
import subprocess

import psutil

from app.core.platform_utils import IS_WINDOWS, run_command
from app.core.result import ToolResult, run_tool, unsupported_result

_PUBLIC_DNS = "1.1.1.1"
_DNS_TEST_HOSTS = ("www.microsoft.com", "www.google.com")


def get_network_adapters() -> ToolResult:
    """Enumerate network interfaces and their up/down status."""

    def _impl() -> dict:
        stats = psutil.net_if_stats()
        adapters = []
        for name, st in stats.items():
            adapters.append(
                {
                    "name": name,
                    "is_up": st.isup,
                    "speed_mbps": st.speed,
                    "mtu": st.mtu,
                }
            )
        up = [a for a in adapters if a["is_up"]]
        return {
            "adapter_count": len(adapters),
            "up_count": len(up),
            "adapters": adapters,
        }

    return run_tool("get_network_adapters", _impl)


def get_ip_configuration() -> ToolResult:
    """Return IPv4/IPv6 addresses per interface."""

    def _impl() -> dict:
        addrs = psutil.net_if_addrs()
        config = {}
        for name, addr_list in addrs.items():
            entries = []
            for a in addr_list:
                family = getattr(a.family, "name", str(a.family))
                if family in ("AF_INET", "AF_INET6"):
                    entries.append(
                        {"family": family, "address": a.address, "netmask": a.netmask}
                    )
            if entries:
                config[name] = entries
        return {"interfaces": config}

    return run_tool("get_ip_configuration", _impl)


def _default_gateway() -> str | None:
    """Best-effort default gateway detection without extra dependencies."""
    try:
        if IS_WINDOWS:
            out = run_command(["ipconfig"], timeout=8)
            for line in out.splitlines():
                if "Default Gateway" in line and ":" in line:
                    candidate = line.split(":", 1)[1].strip()
                    if candidate and candidate[0].isdigit():
                        return candidate
        else:
            out = run_command(["ip", "route"], timeout=8)
            for line in out.splitlines():
                if line.startswith("default via "):
                    return line.split()[2]
    except Exception:  # noqa: BLE001 - best effort
        return None
    return None


def _ping(host: str, count: int = 3, timeout: float = 10.0) -> dict:
    flag = "-n" if IS_WINDOWS else "-c"
    args = ["ping", flag, str(count), host]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            args, capture_output=True, text=True, timeout=timeout, shell=False
        )
        return {
            "host": host,
            "reachable": completed.returncode == 0,
            "output_tail": completed.stdout.strip().splitlines()[-3:],
        }
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"host": host, "reachable": False, "error": str(exc)}


def ping_gateway() -> ToolResult:
    """Ping the default gateway to test local connectivity."""

    def _impl() -> dict:
        gateway = _default_gateway()
        if not gateway:
            return {"gateway": None, "reachable": False, "note": "gateway not found"}
        result = _ping(gateway)
        result["gateway"] = gateway
        return result

    return run_tool("ping_gateway", _impl)


def test_dns() -> ToolResult:
    """Resolve well-known hostnames to test DNS."""

    def _impl() -> dict:
        results = {}
        ok = 0
        for host in _DNS_TEST_HOSTS:
            try:
                socket.setdefaulttimeout(5)
                ip = socket.gethostbyname(host)
                results[host] = {"resolved": True, "address": ip}
                ok += 1
            except OSError as exc:
                results[host] = {"resolved": False, "error": str(exc)}
        return {
            "dns_working": ok > 0,
            "resolved_count": ok,
            "total": len(_DNS_TEST_HOSTS),
            "results": results,
        }

    return run_tool("test_dns", _impl)


def test_internet() -> ToolResult:
    """Test outbound internet reachability via a TCP connect to public DNS."""

    def _impl() -> dict:
        reachable = False
        error = None
        try:
            with socket.create_connection((_PUBLIC_DNS, 53), timeout=5):
                reachable = True
        except OSError as exc:
            error = str(exc)
        return {"internet_reachable": reachable, "target": _PUBLIC_DNS, "error": error}

    return run_tool("test_internet", _impl)


def get_network_profile() -> ToolResult:
    """Return the active network connection profile (Windows only)."""
    if not IS_WINDOWS:
        return unsupported_result(
            "get_network_profile", "Network profiles are a Windows feature"
        )

    def _impl() -> dict:
        from app.core.platform_utils import run_powershell

        out = run_powershell(
            "Get-NetConnectionProfile | "
            "Select-Object Name,InterfaceAlias,NetworkCategory,IPv4Connectivity | "
            "ConvertTo-Json -Compress"
        )
        return {"raw": out.strip()}

    return run_tool("get_network_profile", _impl)
