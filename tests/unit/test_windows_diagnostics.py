"""Windows-path diagnostics and remediations, exercised with mocked system calls.

These run on any OS: the Windows APIs and PowerShell are replaced with fakes
so the parsing, grouping and safety logic is tested deterministically.
"""

from __future__ import annotations

import os
import time

import pytest

from app.core import platform_utils
from app.diagnostics import applications, events, network, performance, services
from app.remediation import _common, network as r_net, storage as r_stor


@pytest.fixture
def as_windows(monkeypatch):
    for module in (platform_utils, applications, events, network, services):
        monkeypatch.setattr(module, "IS_WINDOWS", True, raising=False)


def test_powershell_json_normalises_shapes(monkeypatch):
    monkeypatch.setattr(platform_utils, "IS_WINDOWS", True)
    outputs = iter(["", "null", '{"a": 1}', '[{"a": 1}, {"a": 2}]'])
    monkeypatch.setattr(platform_utils, "run_command", lambda *a, **k: next(outputs))
    assert platform_utils.run_powershell_json("x") == []
    assert platform_utils.run_powershell_json("x") == []
    assert platform_utils.run_powershell_json("x") == [{"a": 1}]
    assert len(platform_utils.run_powershell_json("x")) == 2


def test_powershell_json_rejects_garbage(monkeypatch):
    monkeypatch.setattr(platform_utils, "IS_WINDOWS", True)
    monkeypatch.setattr(platform_utils, "run_command", lambda *a, **k: "Access denied")
    with pytest.raises(platform_utils.CommandError):
        platform_utils.run_powershell_json("x")


def test_decode_falls_back_for_non_utf8():
    assert platform_utils._decode("café".encode("latin-1"))  # no exception
    assert platform_utils._decode(b"") == ""


def test_event_parsing_uses_numeric_levels(as_windows, monkeypatch):
    rows = [
        {"Time": "2026-09-24T10:00:00", "Id": 41, "Level": 1,
         "ProviderName": "Kernel-Power", "Message": "The system rebooted"},
        {"Time": "2026-09-24T09:00:00", "Id": 7000, "Level": 2,
         "ProviderName": "Service Control Manager", "Message": "x" * 900},
    ]
    monkeypatch.setattr(events, "run_powershell_json", lambda *a, **k: rows)
    r = events.get_recent_system_errors()
    assert r["success"]
    assert r["data"]["count"] == 2
    assert r["data"]["critical_count"] == 1
    assert len(r["data"]["events"][1]["message"]) <= 300


def test_crash_parsing_extracts_app_names(as_windows, monkeypatch):
    rows = [{"Message": "Faulting application name: chrome.exe, version: 1"},
            {"Message": "Faulting application name: chrome.exe, version: 1"},
            {"Message": "Faulting application name: teams.exe, version: 2"}]
    monkeypatch.setattr(applications, "run_powershell_json", lambda *a, **k: rows)
    data = applications.get_recent_application_crashes()["data"]
    assert data["count"] == 3
    assert data["apps"][0] == {"name": "chrome.exe", "crashes": 2}


def test_ping_uses_locale_independent_ttl(monkeypatch):
    german = ("Antwort von 192.168.1.1: Bytes=32 Zeit=1ms TTL=64\n" * 3)
    monkeypatch.setattr(network, "run_command", lambda *a, **k: german)
    result = network._ping("192.168.1.1")
    assert result["reachable"] is True and result["replies"] == 3

    unreachable = "Antwort von 10.0.0.5: Zielhost nicht erreichbar.\n" * 3
    monkeypatch.setattr(network, "run_command", lambda *a, **k: unreachable)
    assert network._ping("192.168.1.1")["reachable"] is False


def test_default_gateway_windows_route(as_windows, monkeypatch):
    monkeypatch.setattr(network, "run_powershell_json",
                        lambda *a, **k: [{"NextHop": "192.168.1.1",
                                          "InterfaceAlias": "Wi-Fi"}])
    assert network.default_gateway() == ("192.168.1.1", "Wi-Fi")
    monkeypatch.setattr(network, "run_powershell_json", lambda *a, **k: [])
    assert network.default_gateway() == (None, None)


def test_process_grouping_sums_like_task_manager():
    procs = [
        {"pid": 1, "name": "chrome.exe", "cpu_percent": 1.0, "memory_mb": 1000.0,
         "not_responding": False},
        {"pid": 2, "name": "chrome.exe", "cpu_percent": 2.1, "memory_mb": 3800.0,
         "not_responding": False},
        {"pid": 3, "name": "SearchIndexer.exe", "cpu_percent": 0.0, "memory_mb": 2150.0,
         "not_responding": True},
    ]
    groups = performance._group(procs)
    assert groups[0]["name"] == "chrome.exe"
    assert groups[0]["count"] == 2 and groups[0]["memory_mb"] == 4800.0
    assert groups[1]["display_name"] == "Windows Search indexer"
    assert groups[1]["not_responding"] is True


def test_service_status_health_rules(monkeypatch):
    class FakeService:
        def __init__(self, status, start_type):
            self._d = {"status": status, "start_type": start_type,
                       "display_name": "X", "pid": 1}

        def as_dict(self):
            return self._d

    table = {"WSearch": FakeService("stopped", "automatic"),
             "wuauserv": FakeService("stopped", "manual")}

    def fake_get(name):
        if name not in table:
            raise OSError("service not found")
        return table[name]

    monkeypatch.setattr(services.psutil, "win_service_get", fake_get, raising=False)
    assert services.service_status("WSearch")["healthy"] is False
    assert services.service_status("wuauserv")["healthy"] is True  # demand-start
    missing = services.service_status("bthserv")
    assert missing["status"] == "not_found" and missing["status_text"] == "Not installed"


def test_temp_cleanup_keeps_recent_files(tmp_path):
    old = tmp_path / "old.tmp"
    old.write_bytes(b"x" * 2048)
    two_days = time.time() - 2 * 86400
    os.utime(old, (two_days, two_days))
    recent = tmp_path / "recent.tmp"
    recent.write_bytes(b"y" * 10)

    result = r_stor._clear_dir(tmp_path)
    assert not old.exists()
    assert recent.exists()
    assert result["removed"] == 1 and result["skipped_recent"] == 1


def test_temp_cleanup_on_missing_dir(tmp_path):
    assert r_stor._clear_dir(tmp_path / "nope")["removed"] == 0


def test_restart_service_allowlist_blocks_other_services():
    with pytest.raises(_common.PreconditionError):
        _common.restart_service("WinDefend")


@pytest.mark.parametrize("name", ["Wi-Fi'; Remove-Item C:\\ -Recurse #", 'a"b', "x" * 80, ""])
def test_adapter_name_injection_rejected(name):
    with pytest.raises(_common.PreconditionError):
        r_net.validate_adapter_name(name)


def test_adapter_name_must_exist(monkeypatch):
    monkeypatch.setattr(r_net.psutil, "net_if_stats", lambda: {"Wi-Fi": object()})
    assert r_net.validate_adapter_name("Wi-Fi") == "Wi-Fi"
    with pytest.raises(_common.PreconditionError):
        r_net.validate_adapter_name("Ethernet 9")


def test_memory_details_survives_process_listing_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("NtQuerySystemInformation failed")

    monkeypatch.setattr(performance.psutil, "process_iter", boom)
    assert performance._compressed_memory_mb() is None


def test_display_text_is_cleaned_of_garbage_characters():
    from app.core.winapi import clean_display_text

    assert clean_display_text("NVIDIA App\x008\x01\x02FileVe".split("\x00", 1)[0]) == "NVIDIA App"
    assert clean_display_text("Chrome\x07​") == "Chrome"
    assert clean_display_text("\x00\x01") is None
