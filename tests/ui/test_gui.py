"""Desktop UI tests (offscreen): startup, pages, settings safety and the full flow."""

from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("PySide6")


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("WINFIX_REDUCED_MOTION", "1")
    from app.gui.app import create_application
    from app.gui.theme import manager

    app = create_application()
    manager().apply("light")
    return app


@pytest.fixture
def window(qapp, history):
    from app.gui.window import MainWindow

    win = MainWindow(history=history)
    win.resize(1200, 800)
    win.show()
    qapp.processEvents()
    yield win
    win._force_close = True
    win.close()
    qapp.processEvents()


def _settle(qapp):
    from app.gui.workers import wait_for_idle

    for _ in range(3):
        qapp.processEvents()
        wait_for_idle(10000)
    qapp.processEvents()


def test_every_page_opens_in_both_themes(qapp, window):
    from app.gui.theme import manager
    from app.gui.window import PAGES

    for mode in ("light", "dark"):
        manager().apply(mode)
        for key in PAGES:
            if key == "history_detail":
                continue
            window.navigate(key)
            _settle(qapp)
            assert window.current_key() == key
    manager().apply("light")


def test_back_navigation_returns_to_previous_page(qapp, window):
    window.navigate("history")
    window.navigate("settings")
    window.navigate("settings_ai")
    assert window.nav.current() == "settings"  # subpages keep their section selected
    window.go_back()
    assert window.current_key() == "settings"
    window.go_back()
    assert window.current_key() == "history"


def test_api_key_is_masked_and_not_written_to_settings(qapp, window, tmp_path):
    from app.core import credentials
    from app.core.user_settings import get_store

    window.navigate("settings_ai")
    page = window.page("settings_ai")
    page.cloud.radio.click()
    secret = "sk-test-1234567890abcdefWXYZ"
    page.key_field.setText(secret)
    page._save_key()
    _settle(qapp)
    assert credentials.get_api_key("openai") == secret
    assert secret not in page.key_field.text()
    assert page.key_field.isReadOnly()
    assert page.key_row.description.text().startswith("Saved key ending in WXYZ")
    stored = get_store().path.read_text(encoding="utf-8")
    assert secret not in stored
    assert json.loads(stored)["analysis"] == "cloud"


def test_insecure_endpoint_is_rejected(qapp, window):
    from app.core.user_settings import get_store

    window.navigate("settings_ai")
    page = window.page("settings_ai")
    page.cloud.radio.click()
    page.endpoint.setText("http://example.com/v1")
    page._save_endpoint()
    assert page.endpoint.property("error") == "true"
    assert get_store().load().endpoint == ""


def test_theme_setting_is_saved_and_applied(qapp, window):
    from app.core.user_settings import get_store
    from app.gui.theme import palette

    window.navigate("settings")
    page = window.page("settings")
    page.theme.set_value("dark")
    assert get_store().load().theme == "dark"
    assert palette().name == "dark"
    page.theme.set_value("light")


def test_navigation_collapses_below_1000_px(qapp, window):
    window.resize(900, 700)
    qapp.processEvents()
    assert window.nav.is_compact()
    window.resize(1200, 800)
    qapp.processEvents()
    assert not window.nav.is_compact()


def test_packaged_self_test_passes(qapp, monkeypatch, tmp_path):
    """The same self-test the packaged WinFixAI.exe runs (demo mode, simulated fixes)."""
    from app.gui.app import run_self_test

    monkeypatch.setenv("WINFIX_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    report = tmp_path / "self_test.txt"
    code = run_self_test(report=report, offscreen=True)
    text = report.read_text(encoding="utf-8")
    assert code == 0, text
    assert "FAIL" not in text


def test_empty_history_message_is_fully_visible(qapp, window):
    from app.gui.widgets.composite import EmptyState

    window.navigate("home")
    _settle(qapp)
    empty = window.page("home").findChild(EmptyState)
    assert empty is not None
    label = empty.message
    # The whole sentence fits in the label (it wraps rather than clipping).
    needed = label.heightForWidth(label.width())
    assert label.width() >= 200 and label.height() >= needed


def _ok(data):
    return {"success": True, "data": data, "error": None}


WINDOWS_RESULTS = {
    "system": {
        "get_windows_version": _ok({"is_windows": True, "product": "Windows 11 Pro",
                                    "edition": "Professional", "display_version": "24H2",
                                    "build": 26100, "ubr": 2033, "version": "10.0.26100"}),
        "get_system_info": _ok({"cpu_count_physical": 8, "cpu_count_logical": 16,
                                "memory_total_gb": 31.7, "architecture": "AMD64"}),
        "get_boot_time": _ok({"boot_time": "2026-09-24T08:00:00+00:00",
                              "uptime_seconds": 7200.0}),
        "get_pending_reboot": _ok({"reboot_pending": True, "reasons": ["Windows Update"],
                                   "file_operations_pending": False}),
    },
    "storage": {
        "get_disk_partitions": _ok({"partition_count": 1, "partitions": [
            {"device": "C:\\", "mountpoint": "C:\\", "fstype": "NTFS", "total_gb": 275.0,
             "free_gb": 44.5, "usage_percent": 83.8}]}),
        "get_reclaimable_space": _ok({"temp_mb": 1830.4, "temp_locations": [],
                                      "recycle_bin_mb": 212.0, "recycle_bin_items": 14}),
    },
    "network": {
        "get_network_adapters": _ok({"adapters": [
            {"name": "Wi-Fi", "is_up": True, "speed_mbps": 866, "wireless": True,
             "virtual": False},
            {"name": "Ethernet", "is_up": False, "speed_mbps": 0, "wireless": False,
             "virtual": False}]}),
        "get_ip_configuration": _ok({"interfaces": {"Wi-Fi": [
            {"family": "AF_INET", "address": "192.168.1.20", "netmask": "255.255.255.0"}]}}),
    },
    "services": {
        "get_important_services": _ok({"services": {
            "WSearch": {"name": "WSearch", "label": "Windows Search", "status_text": "Running",
                        "start_type": "automatic", "running": True, "healthy": True},
            "Spooler": {"name": "Spooler", "label": "Print Spooler", "status_text": "Stopped",
                        "start_type": "manual", "running": False, "healthy": False}},
            "unhealthy": ["Spooler"], "healthy": False}),
    },
    "devices": {
        "get_problem_devices": _ok({"count": 1, "devices": [
            {"name": "Unknown USB Device", "class": "USB", "status": "Error",
             "problem": "CM_PROB_FAILED_START", "present": True}]}),
        "get_bluetooth_devices": _ok({"count": 0, "devices": []}),
        "get_driver_information": _ok({"count": 212, "unsigned_count": 0}),
    },
    "events": {
        "get_recent_system_errors": _ok({"events": [
            {"time": "2026-09-24T10:00:00.1234567+05:30", "id": 7000, "level": "Error",
             "source": "Service Control Manager", "message": "The service failed to start."}]}),
        "get_recent_application_errors": _ok({"events": []}),
    },
}


@pytest.mark.parametrize("tab", list(WINDOWS_RESULTS))
def test_diagnostics_tabs_render_windows_data(qapp, window, tab):
    """Every Diagnostics tab renders real-shaped Windows results, partial results
    and missing results without errors."""
    import sys as _sys

    errors = []
    hook, _sys.excepthook = _sys.excepthook, lambda *exc: errors.append(exc)
    try:
        window.navigate("diagnostics")
        page = window.page("diagnostics")
        page.tabs.select(tab)
        _settle(qapp)
        page._render(tab, WINDOWS_RESULTS[tab])
        partial = {t: {"success": True, "data": {}} for t in WINDOWS_RESULTS[tab]}
        page._render(tab, partial)
        failed = {t: {"success": False, "data": None,
                      "error": {"type": "CommandError", "message": "boom"}}
                  for t in WINDOWS_RESULTS[tab]}
        page._render(tab, failed)
        qapp.processEvents()
    finally:
        _sys.excepthook = hook
    assert errors == []
    from app.gui.widgets.status import InfoBar

    shown = [b.title.text() for b in page.pages[tab].findChildren(InfoBar)]
    assert "Some information couldn't be shown." not in shown


def test_diagnostics_export_writes_every_section(qapp, window, tmp_path, monkeypatch):
    import json

    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / "diag.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    window.navigate("diagnostics")
    window.page("diagnostics")._export()
    _settle(qapp)
    report = json.loads(target.read_text(encoding="utf-8"))
    assert set(report["sections"]) == {"system", "storage", "network", "services",
                                       "devices", "events"}
    assert "cpu" in report["performance"]
