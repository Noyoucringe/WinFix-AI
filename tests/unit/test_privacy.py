"""Sanitization of anything that could be sent to a cloud provider."""

import getpass
import socket

from app.core import privacy
from app.core.models import Category
from app.knowledge import troubleshooting
from tests.scenarios import SLOW_PC, results_for


def test_redact_removes_identifiers_and_secrets():
    user, host = getpass.getuser(), socket.gethostname()
    text = (f"C:\\Users\\{user}\\AppData failed on {host} from 192.168.1.23 "
            "mac 00:1A:2B:3C:4D:5E mail me@example.com token=abc123 "
            "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUV id 123e4567-e89b-12d3-a456-426614174000")
    out = privacy.redact(text)
    for leaked in ("192.168.1.23", "00:1A:2B:3C:4D:5E", "me@example.com", "abc123",
                   "sk-ant-api03", "123e4567"):
        assert leaked not in out
    if len(user) >= 3:
        assert user not in out
    if len(host) >= 3:
        assert host not in out
    assert "<ip>" in out and "<email>" in out


def test_payload_honours_toggles():
    results = results_for(SLOW_PC)
    d = troubleshooting.analyze(Category.SLOW_COMPUTER, results)
    minimal, items = privacy.build_payload("My laptop is slow", Category.SLOW_COMPUTER, d,
                                           results, include_process_names=False,
                                           include_event_excerpts=False)
    assert items == [privacy.ITEM_MEASUREMENTS]
    assert "top_apps" not in minimal and "event_excerpts" not in minimal
    assert "Chrome" not in str(minimal)
    assert minimal["measurements"]["memory_percent"] == 73.2

    full, items = privacy.build_payload("My laptop is slow", Category.SLOW_COMPUTER, d,
                                        results, include_process_names=True,
                                        include_event_excerpts=True)
    assert privacy.ITEM_PROCESS_NAMES in items
    assert full["top_apps"][0]["name"] == "Google Chrome"


def test_payload_never_contains_raw_diagnostics():
    results = results_for(SLOW_PC)
    d = troubleshooting.analyze(Category.SLOW_COMPUTER, results)
    payload, _ = privacy.build_payload("slow", Category.SLOW_COMPUTER, d, results,
                                       include_process_names=True,
                                       include_event_excerpts=True)
    assert "pids" not in str(payload) and "hostname" not in str(payload)
