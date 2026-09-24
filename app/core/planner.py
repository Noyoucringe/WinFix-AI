"""Diagnostic planner.

Turns a natural-language problem into a validated :class:`Plan`: a category
and the diagnostic tools to run. Selection comes from the provider (offline
classifier or LLM) but every tool is validated against the registry, so an
unregistered, unsafe or state-changing tool can never enter a plan.
"""

from __future__ import annotations

from app.core.logging_setup import get_logger
from app.core.models import Plan
from app.core.safety import SafetyValidator
from app.core.tool_registry import get_registry
from app.knowledge.categories import GENERAL_TOOLS, get_category_spec
from app.llm.provider import LLMProvider, get_provider

logger = get_logger(__name__)

DEPTHS = ("quick", "standard", "thorough")
QUICK_LIMIT = 4


class Planner:
    def __init__(self, provider: LLMProvider | None = None,
                 safety: SafetyValidator | None = None) -> None:
        self.registry = get_registry()
        self.provider = provider or get_provider()
        self.safety = safety or SafetyValidator(self.registry)

    def plan(self, problem: str, depth: str = "standard") -> Plan:
        category = self.provider.classify(problem)
        spec = get_category_spec(category)
        candidates = self.registry.diagnostic_names()
        selected = self.provider.suggest_tools(problem, category, candidates)
        if spec and depth == "thorough":
            selected = list(selected) + [t for t in spec.thorough_tools if t not in selected]

        valid: list[str] = []
        for name in selected:
            try:
                self.safety.validate_tool_selection(name)
            except Exception as exc:  # noqa: BLE001 - untrusted selection
                logger.warning("dropping invalid planned tool",
                               extra={"component": "planner", "event": "drop",
                                      "tool": str(name)[:60], "status": str(exc)[:120]})
                continue
            if self.safety.is_read_only(name) and name not in valid:
                valid.append(name)

        if not valid:
            valid = [t for t in GENERAL_TOOLS if t in candidates]
        if depth == "quick":
            valid = valid[:QUICK_LIMIT]

        title = spec.title if spec else "General check-up"
        return Plan(
            category=category,
            summary=f"Investigating: {title}",
            diagnostic_tools=valid,
            rationale=(f"Classified the problem as '{title}'. Selected {len(valid)} "
                       "relevant read-only checks."),
        )
