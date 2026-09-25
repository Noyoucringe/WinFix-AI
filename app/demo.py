"""Demo mode (``--demo``): isolated sample data for presentations.

* Uses its own temporary data folder — your real history and settings are
  never read or written.
* For known problems, diagnostics replay measurements recorded on real
  Windows PCs (checks that weren't recorded report "not recorded"); other
  problems and the Diagnostics page measure this PC live (read-only).
* Fixes are simulated. Nothing on this PC is changed.
"""

from __future__ import annotations

import copy
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from app.core.models import Category, Session
from app.core.result import success_result, unsupported_result
from app.demo_evidence import (
    BLUETOOTH_MISSING,
    DNS_BROKEN,
    DNS_FIXED,
    SLOW_PC,
    SLOW_PC_AFTER_FIX_RESOLVED,
    STORAGE_FULL,
    UPDATE_SERVICE_STOPPED,
    WIFI_ROUTER_DOWN,
)
from app.knowledge.categories import classify

BANNER = ("Sample measurements are used and fixes are simulated. "
          "Nothing on this PC is changed.")

WIFI_FIXED = copy.deepcopy(WIFI_ROUTER_DOWN)
WIFI_FIXED["ping_gateway"].update(reachable=True, replies=3, loss_percent=0)
WIFI_FIXED["test_dns"].update(dns_working=True, resolved_count=2)
WIFI_FIXED["test_internet"].update(internet_reachable=True, error=None)

STORAGE_RESOLVED = copy.deepcopy(STORAGE_FULL)
STORAGE_RESOLVED["get_disk_free_space"].update(free_gb=28.4, usage_percent=88.0,
                                               low_space=False)
STORAGE_RESOLVED["get_reclaimable_space"].update(temp_mb=110.0)

UPDATE_FIXED = copy.deepcopy(UPDATE_SERVICE_STOPPED)
UPDATE_FIXED["get_windows_update_status"]["services"]["wuauserv"].update(
    status="running", status_text="Running", running=True, healthy=True)
UPDATE_FIXED["get_windows_update_status"]["healthy"] = True

UPDATE_RESTART_PENDING = copy.deepcopy(UPDATE_FIXED)
UPDATE_RESTART_PENDING["get_pending_reboot"].update(reboot_pending=True,
                                                    reasons=["Windows Update"])

BLUETOOTH_DRIVER = copy.deepcopy(BLUETOOTH_MISSING)
BLUETOOTH_DRIVER["get_bluetooth_devices"] = {
    "count": 2, "adapter_present": True, "problem_count": 1,
    "devices": [{"name": "Intel(R) Wireless Bluetooth(R)", "class": "Bluetooth",
                 "status": "Error", "problem": "CM_PROB_FAILED_START", "present": True},
                {"name": "Surface Headphones", "class": "Bluetooth", "status": "OK",
                 "problem": "", "present": True}]}

SLOW_STARTUP = {
    "get_startup_apps": {"count": 18, "apps": []},
    "get_boot_time": {"boot_time": "2026-08-30T08:00:00+00:00", "uptime_seconds": 3600,
                      "uptime_hours": 1.0, "uptime_days": 0.04},
    "get_disk_usage": SLOW_PC["get_disk_usage"],
    "get_memory_usage": SLOW_PC["get_memory_usage"],
    "get_recent_system_errors": SLOW_PC["get_recent_system_errors"],
}

SCENARIOS = {
    Category.SLOW_COMPUTER: (SLOW_PC, SLOW_PC_AFTER_FIX_RESOLVED),
    Category.HIGH_MEMORY: (SLOW_PC, SLOW_PC_AFTER_FIX_RESOLVED),
    Category.LOW_DISK_SPACE: (STORAGE_FULL, STORAGE_RESOLVED),
    Category.WIFI_DISCONNECTING: (WIFI_ROUTER_DOWN, WIFI_FIXED),
    Category.INTERNET_DOWN: (WIFI_ROUTER_DOWN, WIFI_FIXED),
    Category.DNS_PROBLEMS: (DNS_BROKEN, DNS_FIXED),
    Category.WINDOWS_UPDATE: (UPDATE_SERVICE_STOPPED, UPDATE_FIXED),
    Category.BLUETOOTH: (BLUETOOTH_DRIVER, None),
    Category.STARTUP_PROBLEMS: (SLOW_STARTUP, None),
}


def isolate() -> Path:
    """Point all app data at a fresh temporary folder. Call before startup."""
    folder = Path(tempfile.mkdtemp(prefix="winfix-demo-"))
    os.environ["WINFIX_DATA_DIR"] = str(folder)
    from app.core.config import get_settings

    get_settings.cache_clear()
    return folder


class DemoMode:
    """Serves recorded evidence and simulates fixes on the live registry."""

    def __init__(self, registry) -> None:
        self.registry = registry
        self._original = registry.execute_tool
        self._evidence: dict = {}
        self._after: dict | None = None
        registry.execute_tool = self._execute

    def prepare(self, problem: str) -> None:
        before, after = SCENARIOS.get(classify(problem), ({}, None))
        self.use(before, after)

    def use(self, before: dict, after: dict | None) -> None:
        self._evidence = copy.deepcopy(before)
        self._after = copy.deepcopy(after) if after else None

    def _execute(self, name, arguments=None):
        spec = self.registry.get_tool(name)
        self.registry.validate_arguments(spec, arguments or {})
        if not spec.read_only:
            if self._after is not None:
                self._evidence = copy.deepcopy(self._after)
            return success_result(name, {"simulated": True, "demo": True})
        if name in self._evidence:
            return success_result(name, copy.deepcopy(self._evidence[name]))
        if self._evidence:
            # A recorded scenario stays fully recorded: mixing in live readings
            # from this PC would make the demo depend on the machine it runs on.
            return unsupported_result(name, "Not recorded in this demo scenario.")
        return self._original(name, arguments)

    def live_execute(self, name, arguments=None):
        """Run a read-only tool for real (the Diagnostics page shows this PC)."""
        spec = self.registry.get_tool(name)
        if not spec.read_only:
            raise PermissionError("Demo mode never runs fixes for real.")
        return self._original(name, arguments)

    def restore(self) -> None:
        self.registry.execute_tool = self._original


def _shift(session: Session, delta: timedelta) -> None:
    session.created_at -= delta
    if session.finished_at:
        session.finished_at -= delta
    for event in session.timeline:
        event.at -= delta
    for outcome in session.remediations:
        outcome.timestamp -= delta
        if outcome.approved_at:
            outcome.approved_at -= delta
        if outcome.finished_at:
            outcome.finished_at -= delta
    if session.diagnosis and session.diagnosis.completed_at:
        session.diagnosis.completed_at -= delta
    session.display_id = "WFX-" + session.created_at.astimezone().strftime("%Y%m%d-%H%M")


def seed_history(demo: DemoMode, history) -> None:
    """Create six realistic sample sessions like the design's History page."""
    from app.core.agent import Agent

    agent = Agent(history=None, settle_seconds=0, elevate=False)
    plans = [
        ("My laptop is very slow", SLOW_PC, SLOW_PC_AFTER_FIX_RESOLVED, "apply", 0.1),
        ("Wi-Fi keeps disconnecting", WIFI_ROUTER_DOWN, WIFI_FIXED, "apply", 1),
        ("My storage is almost full", STORAGE_FULL, STORAGE_RESOLVED, "apply", 3),
        ("Windows Update isn't working", UPDATE_RESTART_PENDING, None, "none", 6),
        ("Bluetooth headphones won't connect", BLUETOOTH_DRIVER, None, "decline", 12),
        ("PC takes a long time to start", SLOW_STARTUP, None, "none", 25),
    ]
    for problem, before, after, action, days_ago in plans:
        demo.use(before, after)
        session = agent.diagnose(problem).session
        if action == "apply" and session.proposals:
            agent.remediate_and_verify(session, session.proposals[0], approved=True)
        elif action == "decline":
            agent.decline(session)
        _shift(session, timedelta(days=days_ago, minutes=22))
        history.save_session(session)
    demo.use({}, None)
