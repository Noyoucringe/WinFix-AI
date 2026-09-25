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
