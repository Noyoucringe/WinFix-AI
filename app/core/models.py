"""Pydantic domain models for WinFix AI.

These model the agent's work products: the diagnostic plan, the evidence
shown to the user, the diagnosis and its causes, proposed fixes, before/after
verification, the session timeline, and the full session record kept in
history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _uuid() -> str:
    return uuid4().hex


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Level(str, Enum):
    """Severity of a finding. Always shown with an icon *and* words."""

    OK = "ok"
    INFO = "info"
    CAUTION = "caution"
    CRITICAL = "critical"


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


class SessionResult(str, Enum):
    """The outcome shown in History."""

    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    NOT_RESOLVED = "not_resolved"
    NO_ISSUE = "no_issue"
    STOPPED = "stopped"
    FAILED = "failed"


class Category(str, Enum):
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
    category: Category = Category.UNKNOWN
    summary: str = ""
    diagnostic_tools: list[str] = Field(default_factory=list)
    rationale: str = ""


class EvidenceCard(BaseModel):
    """One measured value shown on the Diagnosis screen."""

    key: str
    label: str
    icon: str = "info"
    value: str
    detail: str = ""
    level: Level = Level.OK
    status_text: str = ""
    progress: float | None = None  # 0..1 meter, when meaningful
    source: str = ""


class Cause(BaseModel):
    """A possible cause, the evidence for it, and the fix linked to it."""

    id: str = ""
    cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    detail: str = ""
    level: Level = Level.CAUTION
    remediation: str | None = None
    sources: list[str] = Field(default_factory=list)

    @property
    def likelihood_word(self) -> str:
        if self.confidence >= 0.75:
            return "likely"
        if self.confidence >= 0.4:
            return "possible"
        return "less likely"


class Diagnosis(BaseModel):
    category: Category = Category.UNKNOWN
    summary: str = ""
    headline: str = ""
    level: Level = Level.OK
    possible_causes: list[Cause] = Field(default_factory=list)
    evidence_cards: list[EvidenceCard] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    recommended_tools: list[str] = Field(default_factory=list)
    analysis_source: str = "local"  # "local" | "cloud"
    ai_status: str = "local"        # "local" | "cloud" | "unavailable"
    ai_message: str = ""
    checks_completed: int = 0
    completed_at: datetime | None = None

    @property
    def top_cause(self) -> Cause | None:
        if not self.possible_causes:
            return None
        return max(self.possible_causes, key=lambda c: c.confidence)

    def cause(self, cause_id: str) -> Cause | None:
        return next((c for c in self.possible_causes if c.id == cause_id), None)


class RemediationProposal(BaseModel):
    """A fix WinFix proposes. Nothing runs until the user approves it."""

    tool: str
    title: str
    reason: str
    risk_level: RiskLevel = RiskLevel.LOW
    requires_admin: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)
    verification_tools: list[str] = Field(default_factory=list)
    consequences: str = ""
    # Plain-language copy for the Recommended fix screen and approval dialog.
    change: str = ""
    summary: str = ""
    description: str = ""
    expected_effect: str = ""
    what_changes: str = ""
    what_unchanged: str = ""
    files_affected: str = "Not affected"
    estimated_time: str = ""
    risk_note: str = ""
    steps: list[str] = Field(default_factory=list)
    technical: str = ""
    cause_id: str | None = None
    evidence_backed: bool = True


class RemediationOutcome(BaseModel):
    tool: str
    approved: bool = False
    executed: bool = False
    success: bool = False
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    elevated: bool | None = None
    approved_at: datetime | None = None
    finished_at: datetime | None = None
    timestamp: datetime = Field(default_factory=now_utc)


class CheckStatus(str, Enum):
    IMPROVED = "improved"
    OK = "ok"
    UNCHANGED = "unchanged"
    WORSE = "worse"
    UNAVAILABLE = "unavailable"


class VerificationCheck(BaseModel):
    """One row of the before/after table."""

    label: str
    before: str
    after: str
    before_level: Level = Level.INFO
    after_level: Level = Level.INFO
    status: CheckStatus = CheckStatus.UNCHANGED


class VerificationResult(BaseModel):
    improved: bool = False            # the original issue is resolved
    action_effective: bool | None = None  # the change itself took effect
    headline: str = ""
    summary: str = ""
    found: str = ""
    note: str = ""
    checks: list[VerificationCheck] = Field(default_factory=list)
    remaining_causes: list[str] = Field(default_factory=list)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    metrics: list[str] = Field(default_factory=list)


class CheckRecord(BaseModel):
    """How one diagnostic check went, for progress rows and history."""

    tool: str
    label: str
    status: str = "queued"  # queued | running | completed | failed | cancelled
    summary: str = ""
    duration_ms: float | None = None
    source: str = ""
    error: str = ""


class TimelineEvent(BaseModel):
    at: datetime = Field(default_factory=now_utc)
    kind: str = "info"  # started | checks | diagnosis | approved | declined | ...
    title: str
    detail: str = ""


class CloudTransmission(BaseModel):
    sent: bool = False
    provider: str | None = None
    endpoint_host: str | None = None
    items: list[str] = Field(default_factory=list)
    at: datetime | None = None


class Session(BaseModel):
    """A full troubleshooting session: the unit of history and audit."""

    id: str = Field(default_factory=_uuid)
    display_id: str = ""
    created_at: datetime = Field(default_factory=now_utc)
    finished_at: datetime | None = None
    problem: str = ""
    status: SessionStatus = SessionStatus.CREATED
    result: SessionResult = SessionResult.IN_PROGRESS
    plan: Plan | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    checks: list[CheckRecord] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None
    proposals: list[RemediationProposal] = Field(default_factory=list)
    approval_status: str = "none"  # none | approved | declined
    remediations: list[RemediationOutcome] = Field(default_factory=list)
    verification: VerificationResult | None = None
    verifications: list[VerificationResult] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    cloud: CloudTransmission = Field(default_factory=CloudTransmission)
    final_outcome: str = ""

    def model_post_init(self, _context: Any) -> None:
        if not self.display_id:
            self.display_id = "WFX-" + self.created_at.astimezone().strftime("%Y%m%d-%H%M")

    def short_diagnosis(self) -> str:
        if not self.diagnosis:
            return ""
        top = self.diagnosis.top_cause
        return top.cause if top else self.diagnosis.headline or self.diagnosis.summary

    def add_event(self, kind: str, title: str, detail: str = "") -> TimelineEvent:
        event = TimelineEvent(kind=kind, title=title, detail=detail)
        self.timeline.append(event)
        return event

    @property
    def changes_made(self) -> int:
        return sum(1 for r in self.remediations if r.executed and r.success)
