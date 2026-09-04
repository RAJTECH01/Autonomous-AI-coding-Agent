from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class TaskCreate(BaseModel):
    project_id: UUID
    title: str = Field(min_length=3, max_length=255)
    requirement_prompt: str = Field(min_length=10, description="Natural language prompt")
    priority: str = Field(default="medium")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    requirement_prompt: Optional[str] = Field(default=None, min_length=10)
    status: Optional[str] = Field(default=None)
    priority: Optional[str] = Field(default=None)


class TaskResponse(BaseModel):
    id: UUID
    project_id: UUID
    creator_id: UUID
    title: str
    requirement_prompt: str
    status: str
    priority: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
