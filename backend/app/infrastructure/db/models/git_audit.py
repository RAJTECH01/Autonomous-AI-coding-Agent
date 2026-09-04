import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer, JSON
from app.infrastructure.db.base import Base


class GitAuditLogModel(Base):
    """Auditable log of all Git operations executed by the agent or system."""
    __tablename__ = "git_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    operation = Column(String(50), nullable=False)
    branch_name = Column(String(255), nullable=False)
    command = Column(Text, nullable=False)
    exit_code = Column(Integer, nullable=False, default=0)
    output_summary = Column(Text, nullable=True)
    protected_branch_checked = Column(Boolean, default=True)
    user_authorized = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GitCommitMetadataModel(Base):
    """Metadata for commits generated during autonomous task runs."""
    __tablename__ = "git_commit_metadata"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    commit_hash = Column(String(64), nullable=False, index=True)
    task_id = Column(String(36), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    branch_name = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    author_name = Column(String(255), nullable=False)
    author_email = Column(String(255), nullable=False)
    files_changed = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
