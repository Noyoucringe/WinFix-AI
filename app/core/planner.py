"""Diagnostic planner.

Turns a natural-language problem into a validated :class:`Plan`: a category
and the set of diagnostic tools to run. Tool selection comes from the provider
(local classifier or LLM), but is always validated against the registry so an
unregistered or unsafe tool name can never enter the plan.
"""

from __future__ import annotations

from app.core.logging_setup import get_logger
from app.core.models import Category, Plan
from app.core.safety import SafetyValidator
from app.core.tool_registry import get_registry
from app.knowledge.categories import get_category_spec
from app.llm.provider import LLMProvider, get_provider

logger = get_logger(__name__)


class Planner:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        safety: SafetyValidator | None = None,
    ) -> None:
        self.registry = get_registry()
        self.provider = provider or get_provider()
        self.safety = safety or SafetyValidator(self.registry)

    def plan(self, problem: str) -> Plan:
        category = self.provider.classify(problem)
        candidate = self.registry.diagnostic_names()
        selected = self.provider.suggest_tools(problem, category, candidate)

        # Validate every selected tool. Drop anything invalid rather than fail.
        valid_tools: list[str] = []
        for name in selected:
            try:
                self.safety.validate_tool_selection(name)
                if self.safety.is_read_only(name):
                    valid_tools.append(name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "dropping invalid planned tool",
                    extra={"component": "planner", "event": "drop", "tool": name,
                           "status": str(exc)},
                )

        if not valid_tools:
            # Safe default: a broad, cheap read-only sweep.
            valid_tools = [t for t in (
                "get_system_info", "get_cpu_usage", "get_memory_usage",
                "get_disk_usage") if t in candidate]

        spec = get_category_spec(category)
        title = spec.title if spec else "General diagnostics"
        return Plan(
            category=category,
            summary=f"Investigating: {title}",
            diagnostic_tools=valid_tools,
            rationale=(
                f"Classified the problem as '{title}'. Selected "
                f"{len(valid_tools)} relevant read-only diagnostics."
            ),
        )
