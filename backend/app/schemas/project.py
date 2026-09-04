from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    repository_url: Optional[str] = Field(default=None, max_length=512)
    default_branch: str = Field(default="main", max_length=100)
    language_stack: str = Field(default="python", max_length=100)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    repository_url: Optional[str] = Field(default=None, max_length=512)
    default_branch: Optional[str] = Field(default=None, max_length=100)
    language_stack: Optional[str] = Field(default=None, max_length=100)


class ProjectResponse(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    slug: str
    description: Optional[str]
    repository_url: Optional[str]
    default_branch: str
    language_stack: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
