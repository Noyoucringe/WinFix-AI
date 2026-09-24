"""Tests for the tool registry."""

import pytest

from app.core.models import RiskLevel
from app.core.result import success_result
from app.core.tool_registry import (
    ToolNotFoundError,
    ToolParameter,
    ToolRegistry,
    ToolSpec,
    ToolValidationError,
)


def _reg():
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="echo",
        function=lambda value="x": success_result("echo", {"value": value}),
        category="test",
        parameters=(ToolParameter("value", "string", "text", False),),
    ))
    return reg


def test_register_and_get():
    reg = _reg()
    assert reg.has("echo")
    assert reg.get_tool("echo").category == "test"


def test_duplicate_registration_rejected():
    reg = _reg()
    with pytest.raises(ValueError):
        reg.register(ToolSpec(name="echo", function=lambda: None))


def test_unknown_tool_raises():
    reg = _reg()
    with pytest.raises(ToolNotFoundError):
        reg.get_tool("missing")


def test_execute_tool():
    reg = _reg()
    r = reg.execute_tool("echo", {"value": "hi"})
    assert r["success"] and r["data"]["value"] == "hi"


def test_argument_validation_unknown_arg():
    reg = _reg()
    with pytest.raises(ToolValidationError):
        reg.execute_tool("echo", {"bad": 1})


def test_argument_validation_type():
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="needs_int",
        function=lambda n=0: success_result("needs_int", {"n": n}),
        parameters=(ToolParameter("n", "integer", "num", True),),
    ))
    with pytest.raises(ToolValidationError):
        reg.execute_tool("needs_int", {"n": "not-int"})
    with pytest.raises(ToolValidationError):
        reg.execute_tool("needs_int", {"n": True})  # bool must not pass as int


def test_missing_required_argument():
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="req",
        function=lambda x=1: success_result("req", {}),
        parameters=(ToolParameter("x", "integer", "", True),),
    ))
    with pytest.raises(ToolValidationError):
        reg.execute_tool("req", {})


def test_timeout_produces_error_result():
    import time

    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="slow",
        function=lambda: (time.sleep(2), success_result("slow", {}))[1],
        timeout=0.1,
    ))
    r = reg.execute_tool("slow")
    assert r["success"] is False
    assert r["error"]["type"] == "TimeoutError"


def test_list_filtering():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="ro", function=lambda: success_result("ro", {}),
                          read_only=True))
    reg.register(ToolSpec(name="rw", function=lambda: success_result("rw", {}),
                          read_only=False, risk_level=RiskLevel.LOW))
    assert [s.name for s in reg.list_tools(read_only=True)] == ["ro"]
    assert [s.name for s in reg.list_tools(read_only=False)] == ["rw"]


def test_json_schema():
    reg = _reg()
    schema = reg.get_tool("echo").json_schema()
    assert schema["name"] == "echo"
    assert "value" in schema["parameters"]["properties"]


def test_global_registry_has_expected_counts():
    from app.core.tool_registry import get_registry

    reg = get_registry()
    assert len(reg.list_tools(read_only=True)) >= 20
    assert len(reg.list_tools(read_only=False)) >= 15
