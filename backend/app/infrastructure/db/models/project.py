import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, ForeignKey, Integer, Boolean, UniqueConstraint, Index, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.db.base import Base, TimestampMixin, SoftDeleteMixin


class ProjectModel(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    repository_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    language_stack: Mapped[str] = mapped_column(String(100), default="python", nullable=False)

    members: Mapped[List["ProjectMemberModel"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    files: Mapped[List["ProjectFileModel"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[List["CodingTaskModel"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectMemberModel(Base, TimestampMixin):
    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="developer", nullable=False)

    project: Mapped["ProjectModel"] = relationship(back_populates="members")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )


class ProjectFileModel(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "project_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_binary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    project: Mapped["ProjectModel"] = relationship(back_populates="files")

    __table_args__ = (
        Index("idx_project_files_path", "project_id", "file_path"),
    )
