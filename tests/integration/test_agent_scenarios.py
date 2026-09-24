"""Integration tests: agent tool selection for the required scenarios."""

import pytest

from app.core.agent import Agent
from app.core.models import Category, SessionStatus
from app.core.planner import Planner


@pytest.mark.parametrize("problem,category,expected_tools", [
    ("My laptop is very slow.", Category.SLOW_COMPUTER,
     {"get_cpu_usage", "get_memory_usage", "get_disk_usage"}),
    ("My Wi-Fi keeps disconnecting.", Category.WIFI_DISCONNECTING,
     {"get_network_adapters", "test_dns", "test_internet"}),
    ("Windows Update isn't working.", Category.WINDOWS_UPDATE,
     {"get_windows_update_status"}),
    ("My disk is full.", Category.LOW_DISK_SPACE,
     {"get_disk_usage", "get_disk_free_space"}),
    ("Bluetooth isn't working.", Category.BLUETOOTH,
     {"get_problem_devices"}),
])
def test_planner_selects_relevant_tools(problem, category, expected_tools):
    plan = Planner().plan(problem)
    assert plan.category == category
    assert expected_tools.issubset(set(plan.diagnostic_tools))


def test_agent_does_not_run_every_tool():
    """The agent reasons about relevance rather than running all diagnostics."""
    from app.core.tool_registry import get_registry

    total = len(get_registry().list_tools(read_only=True))
    result = Agent().diagnose("My laptop is very slow.")
    assert len(result.session.diagnostics) < total


def test_agent_full_diagnosis_flow(history):
    agent = Agent(history=history)
    result = agent.diagnose("My laptop is very slow.")
    s = result.session
    assert s.plan is not None
    assert s.diagnosis is not None
    assert s.status in (SessionStatus.AWAITING_APPROVAL, SessionStatus.DIAGNOSED)
    # Session persisted to history.
    assert history.load_session(s.id) is not None
    # Reasoning steps are user-facing strings, not hidden chain-of-thought.
    kinds = [st.kind for st in result.steps]
    assert "plan" in kinds and "analysis" in kinds


def test_agent_respects_max_steps(monkeypatch):
    agent = Agent()
    agent.max_steps = 2
    result = agent.diagnose("My laptop is very slow.")
    assert len(result.session.diagnostics) <= 2
