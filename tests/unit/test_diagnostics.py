"""Tests for diagnostic tools.

psutil-based tools run everywhere; Windows-only tools degrade gracefully.
Every tool must honour the result contract and never raise.
"""

from app.core.result import ToolResult
from app.diagnostics import network, performance, storage, system


def _assert_contract(r: ToolResult, tool: str):
    assert set(["success", "tool", "data", "error"]).issubset(r.keys())
    assert r["tool"] == tool
    if r["success"]:
        assert r["data"] is not None and r["error"] is None
    else:
        assert r["error"] is not None


def test_cpu_usage_contract():
    r = performance.get_cpu_usage()
    _assert_contract(r, "get_cpu_usage")
    assert r["success"] and "usage_percent" in r["data"]


def test_memory_usage_contract():
    r = performance.get_memory_usage()
    _assert_contract(r, "get_memory_usage")
    assert 0 <= r["data"]["usage_percent"] <= 100


def test_disk_usage_contract():
    r = storage.get_disk_usage()
    _assert_contract(r, "get_disk_usage")
    assert r["data"]["total_gb"] > 0


def test_disk_free_space_flag():
    r = storage.get_disk_free_space()
    _assert_contract(r, "get_disk_free_space")
    assert isinstance(r["data"]["low_space"], bool)


def test_top_processes():
    r = performance.get_top_memory_processes(limit=3)
    _assert_contract(r, "get_top_memory_processes")
    assert len(r["data"]["top_memory_processes"]) <= 3


def test_system_info():
    r = system.get_system_info()
    _assert_contract(r, "get_system_info")
    assert "hostname" in r["data"]


def test_network_adapters():
    r = network.get_network_adapters()
    _assert_contract(r, "get_network_adapters")
    assert "adapters" in r["data"]


def test_dns_test_contract():
    r = network.test_dns()
    _assert_contract(r, "test_dns")
    assert "dns_working" in r["data"]


def test_windows_only_tools_degrade():
    """On non-Windows, Windows tools return an unsupported (non-crashing) error."""
    from app.core.platform_utils import IS_WINDOWS
    from app.diagnostics import devices, services, startup

    for fn, name in [
        (services.get_important_services, "get_important_services"),
        (startup.get_startup_apps, "get_startup_apps"),
        (devices.get_problem_devices, "get_problem_devices"),
    ]:
        r = fn()
        _assert_contract(r, name)
        if not IS_WINDOWS:
            assert r["success"] is False
            assert r["error"]["type"] == "UnsupportedPlatform"


def test_memory_usage_survives_disabled_performance_counters(monkeypatch):
    """psutil.swap_memory() reads PDH counters; when they're broken the memory
    check must still report physical memory."""
    import psutil

    def broken():
        raise RuntimeError("PdhAddEnglishCounterW failed. Performance counters may be disabled.")

    monkeypatch.setattr(psutil, "swap_memory", broken)
    from app.diagnostics.performance import get_memory_usage

    r = get_memory_usage()
    assert r["success"]
    assert 0 <= r["data"]["usage_percent"] <= 100
    assert r["data"]["swap_percent"] is None


def test_process_scan_skips_processes_windows_wont_describe(monkeypatch):
    import psutil

    from app.diagnostics import performance

    class Good:
        pid = 1

        def name(self):
            return "good.exe"

    class Bad:
        pid = 2

        def name(self):
            raise OSError(87, "Invalid parameter")

    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: iter([Bad(), Good()]))
    names = [p.info["name"] for p in performance.iter_processes()]
    assert names == ["good.exe"]
