from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class SessionStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    REPAIRING = "repairing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


from app.domain.entities.human_approval import ExecutionMode


@dataclass
class AgentSession:
    id: str
    project_id: str
    user_id: str
    user_prompt: str
    status: SessionStatus = SessionStatus.PENDING
    execution_mode: ExecutionMode = ExecutionMode.APPROVAL_REQUIRED
    high_risk_flagged: bool = False
    ai_provider: str = "anthropic"
    model_name: str = "claude-3-5-sonnet-20241022"
    max_iterations: int = 20
    current_iteration: int = 0
    execution_summary: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
