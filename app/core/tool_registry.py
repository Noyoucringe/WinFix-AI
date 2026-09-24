"""Centralized tool registry.

The registry is the *only* way the agent can cause anything to happen on the
machine. The LLM may **select** a registered tool by name; it can never
supply code to run. The application owns the implementation, validates the
arguments, enforces timeouts, and executes the function.

This is a core safety boundary: there is no ``eval`` / ``exec`` / arbitrary
shell path anywhere in this module.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.config import get_settings
from app.core.logging_setup import get_logger
from app.core.models import RiskLevel
from app.core.result import ToolResult, error_result, is_success

logger = get_logger(__name__)


@dataclass(frozen=True)
class ToolParameter:
    """Declared parameter for a tool. Used for validation and LLM schemas."""

    name: str
    type: str = "string"  # "string" | "integer" | "number" | "boolean"
    description: str = ""
    required: bool = False
    enum: tuple[Any, ...] | None = None


@dataclass(frozen=True)
class ToolSpec:
    """Metadata + implementation for a single tool."""

    name: str
    function: Callable[..., ToolResult]
    category: str = "general"
    description: str = ""
    read_only: bool = True
    requires_admin: bool = False
    risk_level: RiskLevel = RiskLevel.NONE
    timeout: float = 15.0
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)

    def json_schema(self) -> dict[str, Any]:
        """LLM-facing schema (name/description/parameters)."""
        props: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            entry: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum is not None:
                entry["enum"] = list(p.enum)
            props[p.name] = entry
            if p.required:
                required.append(p.name)
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        }


_PY_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


class ToolValidationError(Exception):
    """Raised when arguments do not satisfy a tool's declared parameters."""


class ToolNotFoundError(Exception):
    """Raised when an unregistered tool is requested."""


class ToolRegistry:
    """Thread-safe registry of diagnostic and remediation tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool")

    # --- registration ------------------------------------------------------
    def register(self, spec: ToolSpec) -> None:
        with self._lock:
            if spec.name in self._tools:
                raise ValueError(f"Tool already registered: {spec.name}")
            self._tools[spec.name] = spec
            logger.debug(
                "registered tool",
                extra={"component": "registry", "event": "register", "tool": spec.name},
            )

    def register_tool(
        self,
        name: str,
        function: Callable[..., ToolResult],
        **kwargs: Any,
    ) -> None:
        self.register(ToolSpec(name=name, function=function, **kwargs))

    # --- lookup ------------------------------------------------------------
    def get_tool(self, name: str) -> ToolSpec:
        with self._lock:
            spec = self._tools.get(name)
        if spec is None:
            raise ToolNotFoundError(name)
        return spec

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._tools

    def list_tools(
        self,
        *,
        category: str | None = None,
        read_only: bool | None = None,
    ) -> list[ToolSpec]:
        with self._lock:
            specs = list(self._tools.values())
        if category is not None:
            specs = [s for s in specs if s.category == category]
        if read_only is not None:
            specs = [s for s in specs if s.read_only is read_only]
        return sorted(specs, key=lambda s: s.name)

    def diagnostic_names(self) -> list[str]:
        return [s.name for s in self.list_tools(read_only=True)]

    def remediation_names(self) -> list[str]:
        return [s.name for s in self.list_tools(read_only=False)]

    def schemas(self, *, read_only: bool | None = None) -> list[dict[str, Any]]:
        return [s.json_schema() for s in self.list_tools(read_only=read_only)]

    # --- validation --------------------------------------------------------
    def validate_arguments(self, spec: ToolSpec, arguments: dict[str, Any]) -> None:
        declared = {p.name: p for p in spec.parameters}
        for key in arguments:
            if key not in declared:
                raise ToolValidationError(
                    f"Unknown argument '{key}' for tool '{spec.name}'"
                )
        for p in spec.parameters:
            if p.name not in arguments:
                if p.required:
                    raise ToolValidationError(
                        f"Missing required argument '{p.name}' for '{spec.name}'"
                    )
                continue
            value = arguments[p.name]
            expected = _PY_TYPES.get(p.type, (object,))
            # bool is a subclass of int; guard integer/number against bools.
            if p.type in ("integer", "number") and isinstance(value, bool):
                raise ToolValidationError(
                    f"Argument '{p.name}' for '{spec.name}' must be {p.type}"
                )
            if not isinstance(value, expected):
                raise ToolValidationError(
                    f"Argument '{p.name}' for '{spec.name}' must be {p.type}"
                )
            if p.enum is not None and value not in p.enum:
                raise ToolValidationError(
                    f"Argument '{p.name}' for '{spec.name}' must be one of {p.enum}"
                )

    # --- execution ---------------------------------------------------------
    def execute_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Validate and execute a registered tool with a timeout.

        Never raises for tool-internal failures: those come back as an
        error result so the engine keeps going. Programming errors
        (unknown tool, bad arguments) do raise, since they indicate a bug
        or a rejected LLM selection that callers handle explicitly.
        """
        arguments = arguments or {}
        spec = self.get_tool(name)
        self.validate_arguments(spec, arguments)

        timeout = spec.timeout or get_settings().default_tool_timeout
        future = self._executor.submit(spec.function, **arguments)
        try:
            result = future.result(timeout=timeout)
        except FuturesTimeout:
            future.cancel()
            logger.warning(
                "tool timed out",
                extra={"component": "registry", "event": "timeout", "tool": name},
            )
            return error_result(name, "TimeoutError", f"Tool '{name}' exceeded {timeout}s")
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "tool raised",
                extra={"component": "registry", "event": "error", "tool": name},
            )
            return error_result(name, type(exc).__name__, str(exc))

        logger.info(
            "tool executed",
            extra={
                "component": "registry",
                "event": "execute",
                "tool": name,
                "status": "ok" if is_success(result) else "fail",
                "duration_ms": result.get("duration_ms"),
            },
        )
        return result


# Global registry populated at import time by register_all().
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Return the process-wide registry, populating it on first use."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        from app.core.registration import register_all

        register_all(_registry)
    return _registry
