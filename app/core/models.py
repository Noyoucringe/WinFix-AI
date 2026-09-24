"""Pydantic domain models for WinFix AI.

These model the agent's reasoning artifacts: the diagnostic plan, the
diagnosis with evidence-backed causes, proposed remediations, verification
outcomes, and the full session record used for audit/history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _uuid() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SessionStatus(str, Enum):
    CREATED = "created"
    DIAGNOSING = "diagnosing"
    DIAGNOSED = "diagnosed"
    AWAITING_APPROVAL = "awaiting_approval"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Category(str, Enum):
    """Troubleshooting categories the agent can classify a problem into."""

    SLOW_COMPUTER = "slow_computer"
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    LOW_DISK_SPACE = "low_disk_space"
    INTERNET_DOWN = "internet_down"
    WIFI_DISCONNECTING = "wifi_disconnecting"
    DNS_PROBLEMS = "dns_problems"
    WINDOWS_UPDATE = "windows_update"
    BLUETOOTH = "bluetooth"
    AUDIO = "audio"
    PRINTER = "printer"
    APP_CRASHES = "app_crashes"
    STARTUP_PROBLEMS = "startup_problems"
    DEVICE_DRIVER = "device_driver"
    WINDOWS_SEARCH = "windows_search"
    UNKNOWN = "unknown"


class Plan(BaseModel):
    """A diagnostic plan: which category and which diagnostic tools to run."""

    category: Category = Category.UNKNOWN
    summary: str = ""
    diagnostic_tools: list[str] = Field(default_factory=list)
    rationale: str = ""


class Cause(BaseModel):
    """A possible cause with a confidence and the evidence supporting it."""

    cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)

    @property
    def likelihood_word(self) -> str:
        if self.confidence >= 0.75:
            return "likely"
        if self.confidence >= 0.4:
            return "possible"
        return "less likely"


class Diagnosis(BaseModel):
    """An evidence-backed diagnosis produced from collected diagnostics."""

    category: Category = Category.UNKNOWN
    summary: str = ""
    possible_causes: list[Cause] = Field(default_factory=list)
    recommended_tools: list[str] = Field(default_factory=list)
    analysis_source: str = "local"  # "local" | "llm"

    @property
    def top_cause(self) -> Cause | None:
        if not self.possible_causes:
            return None
        return max(self.possible_causes, key=lambda c: c.confidence)


class RemediationProposal(BaseModel):
    """A proposed remediation action awaiting user approval."""

    tool: str
    title: str
    reason: str
    risk_level: RiskLevel = RiskLevel.LOW
    requires_admin: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)
    verification_tools: list[str] = Field(default_factory=list)
    consequences: str = ""


class RemediationOutcome(BaseModel):
    """The recorded outcome of executing a remediation tool."""

    tool: str
    approved: bool = False
    executed: bool = False
    success: bool = False
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=_now)


class VerificationResult(BaseModel):
    """Whether the problem improved after remediation."""

    improved: bool = False
    summary: str = ""
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    metrics: list[str] = Field(default_factory=list)


class Session(BaseModel):
    """A full troubleshooting session record (the audit unit)."""

    id: str = Field(default_factory=_uuid)
    created_at: datetime = Field(default_factory=_now)
    problem: str = ""
    status: SessionStatus = SessionStatus.CREATED
    plan: Plan | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    diagnosis: Diagnosis | None = None
    proposals: list[RemediationProposal] = Field(default_factory=list)
    remediations: list[RemediationOutcome] = Field(default_factory=list)
    verification: VerificationResult | None = None
    final_outcome: str = ""

    def short_diagnosis(self) -> str:
        if self.diagnosis:
            return self.diagnosis.summary
        return ""
