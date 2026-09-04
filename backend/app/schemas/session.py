from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class SessionCreate(BaseModel):
    task_id: UUID
    ai_provider: str = Field(default="anthropic")
    model_name: str = Field(default="claude-3-5-sonnet-20241022")
    max_iterations: int = Field(default=15, ge=1, le=50)


class SessionResponse(BaseModel):
    id: UUID
    task_id: UUID
    initiator_id: Optional[UUID]
    status: str
    provider_name: str
    model_name: str
    max_iterations: int
    current_iteration: int
    total_tokens_used: int
    estimated_cost_usd: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
