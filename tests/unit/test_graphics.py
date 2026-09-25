"""GPU / graphics: parsing of the Windows data, evidence rules and classification."""

from __future__ import annotations

import os

import pytest

from app.core.models import Category, Level
from app.diagnostics import graphics
from app.knowledge.categories import classify
from app.knowledge.troubleshooting import analyze
from tests.scenarios import results_for


@pytest.fixture
def as_windows(monkeypatch):
    monkeypatch.setattr(graphics, "IS_WINDOWS", True)


def test_gpu_info_parses_adapters_and_driver_age(as_windows, monkeypatch):
    monkeypatch.setattr(graphics, "run_powershell_json", lambda *a, **k: [
        {"Name": "NVIDIA GeForce RTX 4060", "DriverVersion": "32.0.15.6094",
         "DriverDate": "2020-01-15", "Status": "OK", "ConfigManagerErrorCode": 0,
         "CurrentHorizontalResolution": 2560, "CurrentVerticalResolution": 1440,
         "CurrentRefreshRate": 144},
        {"Name": "Microsoft Basic Display Adapter", "Status": "OK",
         "ConfigManagerErrorCode": 0}])
    data = graphics.get_gpu_info()["data"]
    nvidia, basic = data["adapters"]
    assert nvidia["driver_age_days"] > 365 and nvidia["healthy"]
    assert nvidia["resolution"] == "2560 x 1440"
    assert basic["basic_driver"] is True


def test_gpu_usage_groups_engines_per_app(as_windows, monkeypatch):
    replies = iter([
        [{"Name": f"pid_{os.getpid()}_luid_0x1_phys_0_eng_0_engtype_3D",
          "UtilizationPercentage": 70},
         {"Name": f"pid_{os.getpid()}_luid_0x1_phys_0_eng_1_engtype_3D",
          "UtilizationPercentage": 25},
         {"Name": "pid_999999_luid_0x1_phys_0_eng_5_engtype_VideoDecode",
          "UtilizationPercentage": 10}],
        [{"Name": f"pid_{os.getpid()}_luid_0x1_phys_0", "DedicatedUsage": 512 * 1024 ** 2}],
    ])
    monkeypatch.setattr(graphics, "run_powershell_json", lambda *a, **k: next(replies))
    data = graphics.get_gpu_usage()["data"]
    assert data["engines"]["3D"] == 95.0
    assert data["utilization_percent"] == 95.0
    top = data["top_apps"][0]
    assert top["gpu_percent"] == 70.0 and top["gpu_memory_mb"] == 512.0


def test_display_driver_errors_count_resets(as_windows, monkeypatch):
    monkeypatch.setattr(graphics, "run_powershell_json", lambda *a, **k: [
        {"Time": "2026-09-24T10:00:00.0000000+05:30", "Id": 4101, "ProviderName": "Display",
         "Message": "Display driver nvlddmkm stopped responding and has successfully "
                    "recovered."},
        {"Time": "2026-09-23T10:00:00.0000000+05:30", "Id": 13, "ProviderName": "nvlddmkm",
         "Message": "Graphics Exception"}])
    data = graphics.get_display_driver_errors()["data"]
    assert data["driver_resets"] == 2


def test_gpu_tools_are_unsupported_off_windows(monkeypatch):
    monkeypatch.setattr(graphics, "IS_WINDOWS", False)
    for tool in (graphics.get_gpu_info, graphics.get_gpu_usage,
                 graphics.get_display_driver_errors):
        result = tool()
        assert not result["success"]
        assert result["error"]["type"] == "UnsupportedPlatform"


# --- rules -----------------------------------------------------------------------------
_USER_REPORT = {  # the measurements from the user's "my gpu is laggy" report
    "get_memory_usage": {"usage_percent": 71.1, "total_gb": 15.7, "available_gb": 4.5,
                         "used_gb": 11.2},
    "get_cpu_usage": {"usage_percent": 6.5},
}


def test_gpu_problem_is_classified_as_graphics():
    assert classify("my gpu is laggy") == Category.GRAPHICS


def test_driver_crashes_headline_graphics_lag_not_memory():
    evidence = dict(_USER_REPORT)
    evidence["get_display_driver_errors"] = {"days": 7, "count": 3, "driver_resets": 3,
                                             "events": []}
    evidence["get_gpu_usage"] = {"utilization_percent": 40.0, "engines": {"3D": 40.0},
                                 "top_apps": [{"name": "game.exe", "gpu_percent": 40.0,
                                               "gpu_memory_mb": 3000.0, "count": 1}]}
    d = analyze(Category.GRAPHICS, results_for(evidence))
    assert d.headline == "Your graphics driver keeps crashing and recovering."
    assert d.level == Level.CRITICAL
    keys = [c.key for c in d.evidence_cards]
    assert "gpu" in keys and "gpu_resets" in keys
    assert any("graphics driver" in n.lower() for n in d.notes)


def test_moderate_memory_does_not_headline_a_graphics_problem():
    d = analyze(Category.GRAPHICS, results_for(_USER_REPORT))
    assert d.headline != "Your PC is experiencing memory pressure."
    memory = d.cause("memory_pressure")
    assert memory is not None and memory.level == Level.INFO


def test_busy_gpu_and_background_app_are_reported():
    evidence = dict(_USER_REPORT)
    evidence["get_gpu_usage"] = {"utilization_percent": 97.0, "engines": {"3D": 97.0},
                                 "top_apps": [{"name": "msedge.exe", "gpu_percent": 60.0,
                                               "gpu_memory_mb": 800.0, "count": 5}]}
    d = analyze(Category.GRAPHICS, results_for(evidence))
    ids = {c.id for c in d.possible_causes}
    assert {"gpu_busy", "gpu_background_app"} <= ids
    assert d.headline == "Your graphics card is working at its limit."


def test_missing_driver_is_critical():
    evidence = {"get_gpu_info": {"count": 1, "adapters": [
        {"name": "Microsoft Basic Display Adapter", "basic_driver": True, "healthy": True}]}}
    d = analyze(Category.GRAPHICS, results_for(evidence))
    assert d.headline == "Your graphics card is running without its proper driver."
