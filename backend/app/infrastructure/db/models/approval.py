import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Text, JSON
from app.infrastructure.db.base import Base


class ApprovalAuditLogModel(Base):
    __tablename__ = "approval_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), nullable=False, index=True)
    task_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=True)
    action = Column(String(50), nullable=False)
    execution_mode = Column(String(50), nullable=False)
    high_risk_flagged = Column(Boolean, default=False)
    policy_triggers = Column(JSON, default=list)
    feedback_notes = Column(Text, nullable=True)
    updated_requirements = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
