import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, ForeignKey, Text, Index, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.db.base import Base, TimestampMixin, SoftDeleteMixin


class CodingTaskModel(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "coding_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    creator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    requirement_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="backlog", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)

    project: Mapped["ProjectModel"] = relationship(back_populates="tasks")
    agent_runs: Mapped[List["AgentRunModel"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tasks_project_status", "project_id", "status"),
    )
