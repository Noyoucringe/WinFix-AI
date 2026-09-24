"""Verification engine.

After a remediation runs, re-executes the relevant diagnostics and compares
the evidence before and after to decide whether the problem improved. It never
assumes success — improvement must be shown by the numbers where possible.
"""

from __future__ import annotations

from typing import Any

from app.core.logging_setup import get_logger
from app.core.models import Category, VerificationResult
from app.core.tool_registry import get_registry

logger = get_logger(__name__)


class VerificationEngine:
    def __init__(self) -> None:
        self.registry = get_registry()

    def run(
        self,
        category: Category,
        verification_tools: list[str],
        before: dict[str, Any],
    ) -> VerificationResult:
        """Re-run verification tools and compare against ``before`` evidence."""
        after: dict[str, Any] = {}
        for name in verification_tools:
            if self.registry.has(name):
                after[name] = self.registry.execute_tool(name)

        improved, summary, metrics = self._compare(category, before, after)
        result = VerificationResult(
            improved=improved,
            summary=summary,
            before={k: before.get(k) for k in verification_tools if k in before},
            after=after,
            metrics=metrics,
        )
        logger.info(
            "verification complete",
            extra={"component": "engine", "event": "verify",
                   "status": "improved" if improved else "not_improved"},
        )
        return result

    def _metric(self, results: dict[str, Any], tool: str, key: str) -> float | None:
        r = results.get(tool)
        if r and r.get("success") and r.get("data"):
            value = r["data"].get(key)
            return float(value) if isinstance(value, (int, float)) else None
        return None

    def _compare(
        self, category: Category, before: dict[str, Any], after: dict[str, Any]
    ) -> tuple[bool, str, list[str]]:
        metrics: list[str] = []
        improved_signals = 0
        checked = 0

        comparisons = [
            ("get_cpu_usage", "usage_percent", "CPU usage", False),
            ("get_memory_usage", "usage_percent", "Memory usage", False),
            ("get_disk_free_space", "free_gb", "Free disk space", True),
            ("get_disk_usage", "usage_percent", "Disk usage", False),
        ]
        for tool, key, label, higher_is_better in comparisons:
            b = self._metric(before, tool, key)
            a = self._metric(after, tool, key)
            if b is None or a is None:
                continue
            checked += 1
            delta = a - b
            metrics.append(f"{label}: {b} → {a}")
            if higher_is_better and delta > 0:
                improved_signals += 1
            elif not higher_is_better and delta < 0:
                improved_signals += 1

        # Connectivity/service booleans: reachable/working/running now True.
        bool_checks = [
            ("test_internet", "internet_reachable", "Internet reachability"),
            ("test_dns", "dns_working", "DNS resolution"),
            ("ping_gateway", "reachable", "Gateway reachability"),
        ]
        for tool, key, label in bool_checks:
            a = after.get(tool)
            if a and a.get("success") and a.get("data"):
                checked += 1
                if a["data"].get(key):
                    improved_signals += 1
                    metrics.append(f"{label}: OK")
                else:
                    metrics.append(f"{label}: still failing")

        if checked == 0:
            return (
                False,
                "Could not measure improvement from the available diagnostics.",
                metrics,
            )
        improved = improved_signals > 0
        if improved:
            summary = (
                f"{improved_signals} of {checked} measured signals improved after "
                "the fix."
            )
        else:
            summary = f"None of the {checked} measured signals improved after the fix."
        return improved, summary, metrics
