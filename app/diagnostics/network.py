"""Network diagnostics (read-only).

Adapter and address inspection uses psutil and works on any OS. Connectivity
checks use sockets and the system ``ping`` with fixed arguments. Nothing here
parses localized command text, so results are correct on non-English Windows.
"""

from __future__ import annotations

import re
import socket

import psutil

from app.core.platform_utils import (
    IS_WINDOWS,
    CommandError,
    run_command,
    run_powershell_json,
)
from app.core.result import ToolResult, run_tool, unsupported_result

_PUBLIC_DNS = "1.1.1.1"
_DNS_TEST_HOSTS = ("www.microsoft.com", "www.bing.com")
_WIRELESS_HINTS = ("wi-fi", "wifi", "wireless", "wlan", "wlp", "802.11")
_VIRTUAL_HINTS = ("loopback", "vethernet", "virtualbox", "vmware", "hyper-v",
                  "docker", "bluetooth", "isatap", "teredo", "lo")


def _is_virtual(name: str) -> bool:
    lowered = name.lower()
    return lowered == "lo" or any(h in lowered for h in _VIRTUAL_HINTS if h != "lo")


def get_network_adapters() -> ToolResult:
    """Network interfaces, their link state and addresses."""

    def _impl() -> dict:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        adapters = []
        for name, st in stats.items():
            ipv4 = [a.address for a in addrs.get(name, [])
                    if getattr(a.family, "name", "") == "AF_INET"]
            adapters.append({
                "name": name,
                "is_up": st.isup,
                "speed_mbps": st.speed,
                "mtu": st.mtu,
                "wireless": any(h in name.lower() for h in _WIRELESS_HINTS),
                "virtual": _is_virtual(name),
                "ipv4": ipv4,
            })
        physical = [a for a in adapters if not a["virtual"]]
        return {
            "adapter_count": len(adapters),
            "up_count": sum(1 for a in physical if a["is_up"]),
            "physical_count": len(physical),
            "adapters": adapters,
        }

    return run_tool("get_network_adapters", _impl)


def get_ip_configuration() -> ToolResult:
    """IPv4/IPv6 addresses per interface."""

    def _impl() -> dict:
        config = {}
        for name, addr_list in psutil.net_if_addrs().items():
            entries = []
            for a in addr_list:
                family = getattr(a.family, "name", str(a.family))
                if family in ("AF_INET", "AF_INET6"):
                    entries.append({"family": family, "address": a.address,
                                    "netmask": a.netmask})
            if entries:
                config[name] = entries
        return {"interfaces": config}

    return run_tool("get_ip_configuration", _impl)


def default_gateway() -> tuple[str | None, str | None]:
    """(gateway IP, interface alias) for the default route, if any."""
    try:
        if IS_WINDOWS:
            rows = run_powershell_json(
                "Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue"
                " | Sort-Object RouteMetric | Select-Object -First 1 NextHop,InterfaceAlias"
                " | ConvertTo-Json -Compress",
                timeout=15,
            )
            if rows and rows[0].get("NextHop") and rows[0]["NextHop"] != "0.0.0.0":
                return rows[0]["NextHop"], rows[0].get("InterfaceAlias")
            return None, None
        out = run_command(["ip", "route", "show", "default"], timeout=8)
        match = re.search(r"default via (\S+)(?: dev (\S+))?", out)
        if match:
            return match.group(1), match.group(2)
    except CommandError:
        return None, None
    return None, None


def _ping(host: str, count: int = 3) -> dict:
    if IS_WINDOWS:
        args = ["ping", "-n", str(count), "-w", "1000", host]
    else:
        args = ["ping", "-c", str(count), "-W", "1", host]
    try:
        out = run_command(args, timeout=count * 2 + 5, check=False)
    except CommandError as exc:
        return {"host": host, "reachable": False, "error": str(exc)}
    # "TTL=" / "ttl=" appears only on real echo replies and is not localized,
    # unlike "Reply from" or "Destination host unreachable".
    replies = len(re.findall(r"ttl=", out, re.IGNORECASE))
    return {"host": host, "reachable": replies > 0, "replies": replies, "sent": count,
            "loss_percent": round(100 * (count - min(replies, count)) / count)}


def ping_gateway() -> ToolResult:
    """Ping the default gateway (your router) to test the local network."""

    def _impl() -> dict:
        gateway, interface = default_gateway()
        if not gateway:
            return {"gateway": None, "interface": None, "reachable": False,
                    "note": "No default gateway — the PC is not connected to a network."}
        result = _ping(gateway)
        result.update({"gateway": gateway, "interface": interface})
        return result

    return run_tool("ping_gateway", _impl)


def test_dns() -> ToolResult:
    """Resolve well-known hostnames to test DNS."""

    def _impl() -> dict:
        results, ok = {}, 0
        for host in _DNS_TEST_HOSTS:
            try:
                infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                results[host] = {"resolved": True, "address": infos[0][4][0]}
                ok += 1
            except OSError as exc:
                results[host] = {"resolved": False, "error": str(exc)}
        return {"dns_working": ok > 0, "resolved_count": ok,
                "total": len(_DNS_TEST_HOSTS), "results": results}

    return run_tool("test_dns", _impl)


def test_internet() -> ToolResult:
    """Test outbound reachability with a TCP connection to a public resolver."""

    def _impl() -> dict:
        error = None
        try:
            with socket.create_connection((_PUBLIC_DNS, 53), timeout=5):
                reachable = True
        except OSError as exc:
            reachable, error = False, str(exc)
        return {"internet_reachable": reachable, "target": _PUBLIC_DNS, "error": error}

    return run_tool("test_internet", _impl)


def get_network_profile() -> ToolResult:
    """Active connection profiles (network category and connectivity)."""
    if not IS_WINDOWS:
        return unsupported_result("get_network_profile",
                                  "Network profiles are a Windows feature")

    def _impl() -> dict:
        rows = run_powershell_json(
            "Get-NetConnectionProfile | Select-Object InterfaceAlias,"
            "@{n='Category';e={[string]$_.NetworkCategory}},"
            "@{n='IPv4';e={[string]$_.IPv4Connectivity}} | ConvertTo-Json -Compress"
        )
        return {"profiles": [
            {"interface": r.get("InterfaceAlias"), "category": r.get("Category"),
             "ipv4_connectivity": r.get("IPv4")} for r in rows]}

    return run_tool("get_network_profile", _impl)
