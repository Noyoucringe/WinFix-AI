"""Demo mode: isolated, deterministic, and never changes the PC."""

from __future__ import annotations

import pytest

from app.core.agent import Agent
from app.demo import DemoMode


@pytest.fixture
def demo(registry):
    mode = DemoMode(registry)
    yield mode
    mode.restore()


def test_recorded_scenarios_never_measure_this_pc(demo, monkeypatch):
    live = []
    original = demo._original
    monkeypatch.setattr(demo, "_original",
                        lambda name, arguments=None: live.append(name) or original(name, arguments))
    for problem in ("My laptop is very slow", "Wi-Fi keeps disconnecting",
                    "Windows Update isn't working", "My storage is almost full"):
        demo.prepare(problem)
        agent = Agent(history=None, settle_seconds=0, elevate=False)
        session = agent.diagnose(problem).session
        if session.proposals:
            agent.remediate_and_verify(session, session.proposals[0], approved=True)
    assert live == []


def test_fixes_are_simulated(demo):
    demo.prepare("My laptop is very slow")
    result = demo._execute("restart_windows_search")
    assert result["success"] and result["data"]["simulated"]


def test_live_execute_refuses_fixes(demo):
    with pytest.raises(PermissionError):
        demo.live_execute("flush_dns")

