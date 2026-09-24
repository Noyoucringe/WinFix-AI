"""Recorded evidence for deterministic end-to-end tests.

Each scenario maps diagnostic tool names to the ``data`` a real Windows PC
returned for that situation. ``install`` patches the registry so diagnostics
return these values while everything else (safety, analysis, proposals,
verification) runs for real. Remediation tools are never patched here.
"""

from __future__ import annotations

import copy
from typing import Any

from app.core.result import error_result, success_result
from app.demo_evidence import (
    BLUETOOTH_MISSING,
    DNS_BROKEN,
    DNS_FIXED,
    HEALTHY_PC,
    SCENARIOS,
    SLOW_PC,
    SLOW_PC_AFTER_FIX_RESOLVED,
    SLOW_PC_AFTER_FIX_STILL_HIGH,
    STORAGE_AFTER_CLEANUP,
    STORAGE_FULL,
    UPDATE_SERVICE_STOPPED,
    WIFI_ROUTER_DOWN,
)

__all__ = [
    "BLUETOOTH_MISSING", "DNS_BROKEN", "DNS_FIXED", "HEALTHY_PC", "SCENARIOS", "SLOW_PC",
    "SLOW_PC_AFTER_FIX_RESOLVED", "SLOW_PC_AFTER_FIX_STILL_HIGH", "STORAGE_AFTER_CLEANUP",
    "STORAGE_FULL", "UPDATE_SERVICE_STOPPED", "WIFI_ROUTER_DOWN", "ScenarioRegistry",
    "results_for",
]


def results_for(evidence: dict[str, dict[str, Any]]) -> dict[str, dict]:
    """Wrap raw evidence in the standard result contract."""
    return {tool: success_result(tool, copy.deepcopy(d)) for tool, d in evidence.items()}


class ScenarioRegistry:
    """Swaps diagnostic results for recorded evidence on a live registry."""

    def __init__(self, monkeypatch, registry) -> None:
        self._registry = registry
        self._original = registry.execute_tool
        self._evidence: dict[str, dict] = {}
        self._after: dict[str, dict] | None = None
        self.remediation_calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(registry, "execute_tool", self._execute)

    def use(self, evidence: dict[str, dict[str, Any]],
            after_fix: dict[str, dict[str, Any]] | None = None) -> None:
        """Serve ``evidence``; once any fix runs, serve ``after_fix`` instead."""
        self._evidence = copy.deepcopy(evidence)
        self._after = copy.deepcopy(after_fix) if after_fix is not None else None

    def _execute(self, name, arguments=None):
        spec = self._registry.get_tool(name)
        self._registry.validate_arguments(spec, arguments or {})
        if not spec.read_only:
            # Remediations are recorded, never run, in tests.
            self.remediation_calls.append((name, dict(arguments or {})))
            if self._after is not None:
                self._evidence = self._after
            return success_result(name, {"simulated": True})
        if name in self._evidence:
            return success_result(name, copy.deepcopy(self._evidence[name]))
        return error_result(name, "NotCollected", "Not part of this scenario")
