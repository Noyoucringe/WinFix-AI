"""Diagnostic engine.

Executes a set of read-only diagnostic tools via the registry, collecting
structured evidence. A failing diagnostic never aborts the run — its error is
recorded and the engine continues, so partial evidence is always available.
"""

from __future__ import annotations

from typing import Any, Callable

from app.core.logging_setup import get_logger
from app.core.safety import SafetyValidator
from app.core.tool_registry import get_registry

logger = get_logger(__name__)

ProgressCallback = Callable[[str, dict[str, Any]], None]


class DiagnosticEngine:
    def __init__(self, safety: SafetyValidator | None = None) -> None:
        self.registry = get_registry()
        self.safety = safety or SafetyValidator(self.registry)

    def run(
        self,
        tools: list[str],
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Run each tool, returning ``{tool_name: result}``.

        Only read-only tools are permitted here; a remediation tool passed in
        by mistake is skipped with a recorded error.
        """
        results: dict[str, Any] = {}
        for name in tools:
            try:
                self.safety.validate_tool_selection(name)
                if not self.safety.is_read_only(name):
                    raise ValueError(f"'{name}' is not a read-only diagnostic")
            except Exception as exc:  # noqa: BLE001
                results[name] = {
                    "success": False, "tool": name, "data": None,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
                if progress:
                    progress(name, results[name])
                continue

            result = self.registry.execute_tool(name)
            results[name] = result
            logger.info(
                "diagnostic collected",
                extra={"component": "engine", "event": "diagnostic", "tool": name,
                       "status": "ok" if result.get("success") else "fail"},
            )
            if progress:
                progress(name, result)
        return results
