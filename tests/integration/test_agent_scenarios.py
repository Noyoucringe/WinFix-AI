"""The agent: planning for the five required scenarios, live events, bounds."""

import threading

import pytest

from app.core.agent import Agent
from app.core.models import Category, SessionResult, SessionStatus
from app.core.planner import Planner
from tests.scenarios import BLUETOOTH_MISSING, HEALTHY_PC, SLOW_PC


@pytest.mark.parametrize("problem,category,expected_tools", [
    ("My laptop is very slow", Category.SLOW_COMPUTER,
     {"get_cpu_usage", "get_memory_usage", "get_disk_usage", "get_running_processes",
      "get_startup_apps"}),
    ("My Wi-Fi keeps disconnecting", Category.WIFI_DISCONNECTING,
     {"get_network_adapters", "ping_gateway", "test_dns", "test_internet"}),
    ("My storage is almost full", Category.LOW_DISK_SPACE,
     {"get_disk_free_space", "get_reclaimable_space"}),
    ("Windows Update isn't working", Category.WINDOWS_UPDATE,
     {"get_windows_update_status", "get_pending_reboot"}),
    ("Bluetooth isn't working", Category.BLUETOOTH,
     {"get_bluetooth_devices", "get_problem_devices"}),
])
def test_planner_selects_relevant_tools(problem, category, expected_tools):
    plan = Planner().plan(problem)
    assert plan.category == category
    assert expected_tools.issubset(set(plan.diagnostic_tools))


def test_slow_pc_runs_the_seven_design_checks():
    plan = Planner().plan("My laptop is very slow")
    assert plan.diagnostic_tools == [
        "get_cpu_usage", "get_memory_usage", "get_disk_usage", "get_running_processes",
        "get_startup_apps", "get_important_services", "get_recent_system_errors"]


def test_depth_changes_how_much_is_collected():
    quick = Planner().plan("My laptop is very slow", "quick").diagnostic_tools
    thorough = Planner().plan("My laptop is very slow", "thorough").diagnostic_tools
    assert len(quick) < 7 < len(thorough)


def test_agent_does_not_run_every_tool(scenario):
    from app.core.tool_registry import get_registry

    scenario.use(SLOW_PC)
    total = len(get_registry().list_tools(read_only=True))
    session = Agent().diagnose("My laptop is very slow").session
    assert len(session.diagnostics) < total


def test_live_events_follow_the_progress_screen(scenario):
    scenario.use(SLOW_PC)
    events = []
    Agent().diagnose("My laptop is very slow", events=events.append)
    kinds = [e.kind for e in events]
    assert kinds[0] == "plan"
    assert kinds.count("check_started") == kinds.count("check_finished") >= 7
    assert kinds[-2:] == ["analyzing", "diagnosed"]
    first = next(e for e in events if e.kind == "check_finished")
    assert first.data["record"].summary == "Current utilization: 11%"


def test_cancel_stops_between_checks(scenario, history):
    scenario.use(SLOW_PC)
    cancel = threading.Event()

    def on_event(event):
        if event.kind == "check_finished" and event.tool == "get_disk_usage":
            cancel.set()

    session = Agent(history=history).diagnose("My laptop is very slow", events=on_event,
                                              cancel=cancel).session
    assert session.status == SessionStatus.CANCELLED
    assert session.result == SessionResult.STOPPED
    statuses = [c.status for c in session.checks]
    assert statuses[:3] == ["completed"] * 3
    assert set(statuses[3:]) == {"cancelled"}
    assert history.load_session(session.id).result == SessionResult.STOPPED


def test_healthy_pc_ends_with_no_issue(scenario):
    scenario.use(HEALTHY_PC)
    session = Agent().diagnose("My laptop is very slow").session
    assert session.result == SessionResult.NO_ISSUE
    assert session.proposals == []


def test_agent_respects_max_steps(scenario):
    scenario.use(SLOW_PC)
    agent = Agent()
    agent.max_steps = 2
    session = agent.diagnose("My laptop is very slow").session
    assert len(session.diagnostics) <= 2


def test_follow_up_checks_are_evidence_driven(scenario, monkeypatch):
    from app.core import agent as agent_module
    from app.llm import provider as provider_module

    monkeypatch.setattr(provider_module, "IS_WINDOWS", True)
    monkeypatch.setattr(agent_module, "IS_WINDOWS", True)
    scenario.use(SLOW_PC)
    session = Agent().diagnose("My laptop is very slow").session
    extra = [c.tool for c in session.checks[7:]]
    # Memory is high, so the agent looks closer at the Search indexer.
    assert "get_search_indexer_status" in extra
    assert len(session.diagnostics) <= 10


def test_bluetooth_scenario_explains_without_a_fix(scenario):
    scenario.use(BLUETOOTH_MISSING)
    session = Agent().diagnose("Bluetooth isn't working").session
    assert session.diagnosis.headline == "No Bluetooth adapter was found."
    assert session.proposals == []
    assert session.result == SessionResult.NOT_RESOLVED


def test_session_has_design_style_id(scenario):
    scenario.use(HEALTHY_PC)
    session = Agent().diagnose("My laptop is very slow").session
    assert session.display_id.startswith("WFX-") and len(session.display_id) == 17
