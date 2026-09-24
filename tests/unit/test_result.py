"""Tests for the standard tool result contract."""

from app.core.result import (
    error_result,
    is_success,
    run_tool,
    success_result,
    unsupported_result,
)


def test_success_result_shape():
    r = success_result("t", {"a": 1}, duration_ms=12.345)
    assert r["success"] is True
    assert r["tool"] == "t"
    assert r["data"] == {"a": 1}
    assert r["error"] is None
    assert r["duration_ms"] == 12.35
    assert "timestamp" in r and r["tool_version"] == "1.0"


def test_error_result_shape():
    r = error_result("t", "ValueError", "boom")
    assert r["success"] is False
    assert r["data"] is None
    assert r["error"] == {"type": "ValueError", "message": "boom"}


def test_unsupported_result_is_failure():
    r = unsupported_result("t", "no windows")
    assert r["success"] is False
    assert r["error"]["type"] == "UnsupportedPlatform"


def test_run_tool_captures_exceptions():
    def boom():
        raise KeyError("nope")

    r = run_tool("t", boom)
    assert r["success"] is False
    assert r["error"]["type"] == "KeyError"
    assert r["duration_ms"] is not None


def test_run_tool_success_and_timing():
    r = run_tool("t", lambda: {"ok": True})
    assert is_success(r)
    assert r["data"] == {"ok": True}
