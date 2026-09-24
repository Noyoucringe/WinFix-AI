"""Request/response schemas for the WinFix API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.models import (
    Diagnosis,
    Plan,
    RemediationProposal,
    VerificationResult,
)


class DiagnoseRequest(BaseModel):
    problem: str = Field(min_length=1, max_length=2000)


class AgentStepModel(BaseModel):
    kind: str
    message: str
    tool: str | None = None
    ok: bool | None = None


class DiagnoseResponse(BaseModel):
    session_id: str
    plan: Plan | None = None
    diagnosis: Diagnosis | None = None
    proposals: list[RemediationProposal] = []
    status: str
    steps: list[AgentStepModel] = []


class ApproveRequest(BaseModel):
    session_id: str
    tool: str


class ApproveResponse(BaseModel):
    session_id: str
    tool: str
    proposal: RemediationProposal
    approvable: bool = True


class ExecuteRequest(BaseModel):
    session_id: str
    tool: str
    approved: bool = False
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    session_id: str
    status: str
    executed: bool
    success: bool
    verification: VerificationResult | None = None
    final_outcome: str = ""


class VerifyRequest(BaseModel):
    session_id: str


class HistoryItem(BaseModel):
    id: str
    created_at: str
    problem: str
    category: str | None = None
    status: str | None = None
    diagnosis: str | None = None
    fix: str | None = None
    outcome: str | None = None


class ToolInfo(BaseModel):
    name: str
    category: str
    description: str
    read_only: bool
    risk_level: str
    requires_admin: bool


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    llm_available: bool
    diagnostic_tools: int
    remediation_tools: int
    platform: str
