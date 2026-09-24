"""FastAPI application exposing the WinFix agent workflow.

The backend orchestrates diagnosis, approval, remediation, and verification.
It intentionally holds no unrestricted access to the machine: it only invokes
registered tools through the same safety-checked registry the rest of the app
uses. In a client/server deployment the Windows-specific tools execute on the
local client; this server provides orchestration and history.
"""

from __future__ import annotations

import platform

from fastapi import FastAPI, HTTPException

from app.api.schemas import (
    AgentStepModel,
    ApproveRequest,
    ApproveResponse,
    DiagnoseRequest,
    DiagnoseResponse,
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    HistoryItem,
    ToolInfo,
    VerifyRequest,
)
from app.core.agent import Agent
from app.core.config import get_settings
from app.core.history import HistoryStore
from app.core.models import Session, SessionStatus
from app.core.safety import ApprovalRequiredError, SafetyError
from app.core.tool_registry import get_registry
from app.core.verification_engine import VerificationEngine

app = FastAPI(title="WinFix AI", version="1.0.0")

_history = HistoryStore()


def _agent() -> Agent:
    # A server process must never raise UAC prompts; admin-only fixes report
    # "access denied" instead unless the server itself runs elevated.
    return Agent(history=_history, elevate=False)


def _load_session(session_id: str) -> Session:
    session = _history.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    reg = get_registry()
    from app.llm.provider import get_provider

    provider = get_provider()
    return HealthResponse(
        status="ok",
        llm_provider=provider.name,
        llm_available=provider.available,
        diagnostic_tools=len(reg.list_tools(read_only=True)),
        remediation_tools=len(reg.list_tools(read_only=False)),
        platform=platform.system(),
    )


@app.get("/api/tools", response_model=list[ToolInfo])
def list_tools() -> list[ToolInfo]:
    reg = get_registry()
    return [
        ToolInfo(
            name=s.name,
            category=s.category,
            description=s.description,
            read_only=s.read_only,
            risk_level=s.risk_level.value,
            requires_admin=s.requires_admin,
        )
        for s in reg.list_tools()
    ]


@app.post("/api/diagnose", response_model=DiagnoseResponse)
def diagnose(req: DiagnoseRequest) -> DiagnoseResponse:
    result = _agent().diagnose(req.problem)
    s = result.session
    return DiagnoseResponse(
        session_id=s.id,
        plan=s.plan,
        diagnosis=s.diagnosis,
        proposals=s.proposals,
        status=s.status.value,
        steps=[AgentStepModel(kind=st.kind, message=st.message, tool=st.tool, ok=st.ok)
               for st in result.steps],
    )


# Alias: /api/agent/run behaves like diagnose (full agent workflow up to approval).
@app.post("/api/agent/run", response_model=DiagnoseResponse)
def agent_run(req: DiagnoseRequest) -> DiagnoseResponse:
    return diagnose(req)


@app.post("/api/remediation/approve", response_model=ApproveResponse)
def approve(req: ApproveRequest) -> ApproveResponse:
    session = _load_session(req.session_id)
    proposal = next((p for p in session.proposals if p.tool == req.tool), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found for session")
    return ApproveResponse(session_id=session.id, tool=req.tool, proposal=proposal)


@app.post("/api/remediation/execute", response_model=ExecuteResponse)
def execute(req: ExecuteRequest) -> ExecuteResponse:
    session = _load_session(req.session_id)
    proposal = next((p for p in session.proposals if p.tool == req.tool), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found for session")
    try:
        updated = _agent().remediate_and_verify(
            session, proposal, approved=req.approved, arguments=req.arguments
        )
    except ApprovalRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    last = updated.remediations[-1]
    return ExecuteResponse(
        session_id=updated.id,
        status=updated.status.value,
        executed=last.executed,
        success=last.success,
        verification=updated.verification,
        final_outcome=updated.final_outcome,
    )


@app.post("/api/verify", response_model=ExecuteResponse)
def verify(req: VerifyRequest) -> ExecuteResponse:
    """Re-run the verification for the most recent fix in a session."""
    session = _load_session(req.session_id)
    if not session.remediations:
        raise HTTPException(status_code=400, detail="No fix has been applied in this session")
    last = session.remediations[-1]
    proposal = next((p for p in session.proposals if p.tool == last.tool), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found for session")
    verification = VerificationEngine().run(session, proposal, last)
    session.verification = verification
    session.verifications.append(verification)
    session.status = (SessionStatus.RESOLVED if verification.improved
                      else SessionStatus.UNRESOLVED)
    session.final_outcome = f"{verification.headline} {verification.summary}".strip()
    _history.save_session(session)
    return ExecuteResponse(
        session_id=session.id,
        status=session.status.value,
        executed=False,
        success=verification.improved,
        verification=verification,
        final_outcome=session.final_outcome,
    )


@app.get("/api/history", response_model=list[HistoryItem])
def history(limit: int = 50) -> list[HistoryItem]:
    return [HistoryItem(**row) for row in _history.list_sessions(limit=limit)]


@app.get("/api/history/{session_id}")
def history_detail(session_id: str) -> dict:
    payload = _history.get_session(session_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return payload


def run() -> None:  # pragma: no cover - server entrypoint
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":  # pragma: no cover
    run()
