import uuid
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.session import AgentSession, SessionStatus
from app.domain.entities.human_approval import ExecutionMode, ApprovalAction
from app.infrastructure.ai_providers.provider_factory import AIProviderFactory
from app.infrastructure.db.session import get_db
from app.infrastructure.sandbox.docker_sandbox import DockerSandboxAdapter
from app.application.agent.state_machine import AgentStateMachine
from app.api.v1.endpoints.auth import get_current_user
from app.core.exceptions import ResourceNotFoundError
from app.core.permissions import ProjectRole
from app.schemas.approval import ApprovalDecisionRequest, ApprovalDecisionResponse
from app.schemas.auth import UserResponse
from app.services.project_service import ProjectService
from app.core.logging import logger

router = APIRouter()

# In-memory session database for active runtime state
SESSIONS_DB: Dict[str, AgentSession] = {}
STATE_MACHINES_DB: Dict[str, AgentStateMachine] = {}
SANDBOX_ADAPTER = DockerSandboxAdapter()


class CreateSessionRequest(BaseModel):
    project_id: uuid.UUID = Field(description="Project the run belongs to; membership is enforced")
    prompt: str = Field(min_length=1, description="Natural language software requirement")
    execution_mode: str = Field(default="APPROVAL_REQUIRED", description="Execution mode: PLAN_ONLY | APPROVAL_REQUIRED | AUTONOMOUS")
    ai_provider: str = Field(default="anthropic", description="AI Provider: anthropic | openai | gemini")
    model_name: str = Field(default="claude-3-5-sonnet-20241022")
    max_iterations: int = Field(default=15, ge=1, le=50)


class SessionResponse(BaseModel):
    session_id: str
    project_id: str
    status: str
    execution_mode: str
    high_risk_flagged: bool = False
    user_prompt: str
    ai_provider: str
    model_name: str
    current_iteration: int
    execution_summary: Dict[str, Any]


async def run_agent_background_task(session: AgentSession, state_machine: AgentStateMachine):
    try:
        await state_machine.run_autonomous_loop()
        session.status = SessionStatus(state_machine.run.state.value.lower()) if hasattr(SessionStatus, state_machine.run.state.value) else SessionStatus.EXECUTING
        session.execution_summary = state_machine.run.execution_summary
        await SANDBOX_ADAPTER.destroy_sandbox(state_machine.sandbox_id)
    except Exception as e:
        logger.error("Agent execution loop failed", session_id=session.id, error=str(e))
        session.status = SessionStatus.FAILED
        session.execution_summary = {"error": str(e)}


def _load_session_for_caller(session_id: str, current_user: UserResponse) -> AgentStateMachine:
    """Resolve a run the caller is allowed to act on.

    Both "unknown id" and "someone else's run" answer 404, so session ids are not
    enumerable (findings AUTHZ-01, AUTHZ-09).
    """
    session = SESSIONS_DB.get(session_id)
    machine = STATE_MACHINES_DB.get(session_id)
    is_admin = current_user.role in ("admin", "administrator")
    if not session or not machine or (session.user_id != str(current_user.id) and not is_admin):
        raise HTTPException(status_code=404, detail="Agent session not found")
    return machine


@router.post("/sessions", response_model=SessionResponse)
async def create_agent_session(
    req: CreateSessionRequest,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_id = str(uuid.uuid4())
    mode = ExecutionMode(req.execution_mode) if req.execution_mode in ExecutionMode.__members__ else ExecutionMode.APPROVAL_REQUIRED

    # The run must belong to a project the caller can actually contribute to
    # (finding AUTHZ-08). Raises 404 when absent or not visible to the caller.
    await ProjectService(db).get_project_by_id(
        project_id=req.project_id,
        requesting_user_id=current_user.id,
        requesting_user_role=current_user.role,
        required_role=ProjectRole.MEMBER,
    )

    session = AgentSession(
        id=session_id,
        project_id=str(req.project_id),
        user_id=str(current_user.id),
        user_prompt=req.prompt,
        status=SessionStatus.PENDING,
        execution_mode=mode,
        ai_provider=req.ai_provider,
        model_name=req.model_name,
        max_iterations=req.max_iterations,
    )
    
    provider = AIProviderFactory.get_provider(session.ai_provider)
    sandbox_id = await SANDBOX_ADAPTER.create_sandbox(session.id, workspace_path="")

    state_machine = AgentStateMachine(
        task_id=session_id,
        user_prompt=req.prompt,
        provider=provider,
        sandbox=SANDBOX_ADAPTER,
        sandbox_id=sandbox_id,
        execution_mode=mode,
        provider_name=req.ai_provider,
        model_name=req.model_name,
    )

    SESSIONS_DB[session_id] = session
    STATE_MACHINES_DB[session_id] = state_machine

    background_tasks.add_task(run_agent_background_task, session, state_machine)
    
    return SessionResponse(
        session_id=session.id,
        project_id=session.project_id,
        status=session.status.value,
        execution_mode=session.execution_mode.value,
        high_risk_flagged=session.high_risk_flagged,
        user_prompt=session.user_prompt,
        ai_provider=session.ai_provider,
        model_name=session.model_name,
        current_iteration=session.current_iteration,
        execution_summary=session.execution_summary,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_agent_session(session_id: str, current_user: UserResponse = Depends(get_current_user)):
    sm = _load_session_for_caller(session_id, current_user)
    session = SESSIONS_DB[session_id]
    high_risk = sm.run.high_risk_flagged if sm else False

    return SessionResponse(
        session_id=session.id,
        project_id=session.project_id,
        status=session.status.value,
        execution_mode=session.execution_mode.value,
        high_risk_flagged=high_risk,
        user_prompt=session.user_prompt,
        ai_provider=session.ai_provider,
        model_name=session.model_name,
        current_iteration=session.current_iteration,
        execution_summary=session.execution_summary,
    )


@router.post("/sessions/{session_id}/approve", response_model=ApprovalDecisionResponse)
async def approve_session_plan(session_id: str, current_user: UserResponse = Depends(get_current_user)):
    sm = _load_session_for_caller(session_id, current_user)

    try:
        await sm.handle_user_approval(approver_id=str(current_user.id), approver_role=current_user.role)
        return ApprovalDecisionResponse(
            run_id=sm.run.id,
            task_id=session_id,
            new_state=sm.run.state.value,
            action_taken="APPROVE",
            high_risk_flagged=sm.run.high_risk_flagged,
            message="Plan approved successfully. Transitioning to IMPLEMENTING.",
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/sessions/{session_id}/reject", response_model=ApprovalDecisionResponse)
async def reject_session_plan(
    session_id: str,
    req: ApprovalDecisionRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    sm = _load_session_for_caller(session_id, current_user)

    try:
        await sm.handle_user_rejection(feedback_notes=req.feedback_notes)
        return ApprovalDecisionResponse(
            run_id=sm.run.id,
            task_id=session_id,
            new_state=sm.run.state.value,
            action_taken="REJECT",
            high_risk_flagged=sm.run.high_risk_flagged,
            message="Plan rejected. Returning to PLANNING state for revision.",
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/sessions/{session_id}/cancel", response_model=ApprovalDecisionResponse)
async def cancel_session_run(session_id: str, current_user: UserResponse = Depends(get_current_user)):
    sm = _load_session_for_caller(session_id, current_user)

    await sm.handle_user_cancellation()
    return ApprovalDecisionResponse(
        run_id=sm.run.id,
        task_id=session_id,
        new_state=sm.run.state.value,
        action_taken="CANCEL",
        high_risk_flagged=sm.run.high_risk_flagged,
        message="Execution run cancelled by user decision.",
    )


@router.post("/sessions/{session_id}/modify-requirements", response_model=ApprovalDecisionResponse)
async def modify_session_requirements(
    session_id: str,
    req: ApprovalDecisionRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    sm = _load_session_for_caller(session_id, current_user)

    if not req.updated_requirement_prompt:
        raise HTTPException(status_code=400, detail="updated_requirement_prompt is required")

    await sm.handle_modify_requirements(req.updated_requirement_prompt)
    return ApprovalDecisionResponse(
        run_id=sm.run.id,
        task_id=session_id,
        new_state=sm.run.state.value,
        action_taken="MODIFY_REQUIREMENTS",
        high_risk_flagged=sm.run.high_risk_flagged,
        message="Requirement prompt updated. Resetting to ANALYZING state.",
    )
