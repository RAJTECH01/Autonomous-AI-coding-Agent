from typing import Optional, List
from pydantic import BaseModel, Field
from app.domain.entities.human_approval import ExecutionMode, ApprovalAction, HighRiskCategory


class ApprovalDecisionRequest(BaseModel):
    action: ApprovalAction = Field(..., description="Action: APPROVE | REJECT | CANCEL | MODIFY_REQUIREMENTS")
    feedback_notes: Optional[str] = Field(default=None, description="Optional feedback notes for plan rejection")
    updated_requirement_prompt: Optional[str] = Field(default=None, description="Updated requirement prompt when modifying requirements")


class ApprovalDecisionResponse(BaseModel):
    run_id: str
    task_id: str
    new_state: str
    action_taken: str
    high_risk_flagged: bool = False
    message: str


class AuditLogRecordResponse(BaseModel):
    id: str
    run_id: str
    task_id: str
    user_id: Optional[str] = None
    action: str
    execution_mode: str
    high_risk_flagged: bool = False
    policy_triggers: List[str] = []
    feedback_notes: Optional[str] = None
    updated_requirements: Optional[str] = None
    timestamp: str
