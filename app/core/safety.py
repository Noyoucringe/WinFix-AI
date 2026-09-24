"""Safety layer.

Central place that enforces the non-negotiable safety rules:

* Only **registered** tools can run (no arbitrary command strings).
* Remediation tools (``read_only == False``) require **explicit approval**.
* Tool arguments must satisfy the tool's declared parameter schema.
* The agent loop is **bounded** (max steps).
* Remediation attempts are **bounded** (max attempts).

The safety validator is used by the agent, the remediation engine, and the
API layer so the rules hold no matter which entry point is used.
"""

from __future__ import annotations

import re

from app.core.config import get_settings
from app.core.logging_setup import get_logger
from app.core.tool_registry import (
    ToolNotFoundError,
    ToolRegistry,
    ToolValidationError,
    get_registry,
)

logger = get_logger(__name__)

# Patterns that indicate someone tried to smuggle a raw command instead of a
# registered tool name. Registered tool names are simple identifiers.
_SHELL_PATTERN = re.compile(r"[;&|`$><\n]|\.\.|/|\\|\bpowershell\b|\bcmd\b|\brm\b",
                            re.IGNORECASE)
_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class SafetyError(Exception):
    """Raised when an action violates a safety rule."""


class ApprovalRequiredError(SafetyError):
    """Raised when a remediation is attempted without explicit approval."""


class SafetyValidator:
    """Validates tool selections and remediation approvals against the rules."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or get_registry()
        settings = get_settings()
        self.max_agent_steps = settings.max_agent_steps
        self.max_remediation_attempts = settings.max_remediation_attempts

    # --- tool selection ----------------------------------------------------
    def is_valid_tool_name(self, name: str) -> bool:
        return bool(_VALID_NAME.match(name)) and not _SHELL_PATTERN.search(name)

    def validate_tool_selection(self, name: str, arguments: dict | None = None) -> None:
        """Ensure an LLM-selected tool is a real, registered tool with valid
        arguments. Rejects anything resembling a raw command.
        """
        if not isinstance(name, str) or not self.is_valid_tool_name(name):
            raise SafetyError(f"Rejected unsafe tool selection: {name!r}")
        if not self.registry.has(name):
            raise SafetyError(f"Rejected unregistered tool: {name!r}")
        spec = self.registry.get_tool(name)
        try:
            self.registry.validate_arguments(spec, arguments or {})
        except (ToolValidationError, ToolNotFoundError) as exc:
            raise SafetyError(str(exc)) from exc

    def is_read_only(self, name: str) -> bool:
        return self.registry.get_tool(name).read_only

    # --- remediation -------------------------------------------------------
    def validate_remediation(
        self,
        name: str,
        *,
        approved: bool,
        arguments: dict | None = None,
    ) -> None:
        """Validate a remediation before execution.

        Enforces registration, argument validity, that the tool really is a
        remediation tool, and that the user explicitly approved it.
        """
        self.validate_tool_selection(name, arguments)
        spec = self.registry.get_tool(name)
        if spec.read_only:
            raise SafetyError(
                f"'{name}' is a read-only diagnostic, not a remediation action"
            )
        if not approved:
            logger.warning(
                "remediation blocked: not approved",
                extra={"component": "safety", "event": "approval_missing", "tool": name},
            )
            raise ApprovalRequiredError(
                f"Remediation '{name}' requires explicit user approval"
            )

    # --- loop / attempt bounds --------------------------------------------
    def check_agent_step(self, step: int) -> None:
        if step >= self.max_agent_steps:
            raise SafetyError(
                f"Agent exceeded maximum steps ({self.max_agent_steps})"
            )

    def check_remediation_attempt(self, attempt: int) -> None:
        if attempt >= self.max_remediation_attempts:
            raise SafetyError(
                f"Exceeded maximum remediation attempts ({self.max_remediation_attempts})"
            )
