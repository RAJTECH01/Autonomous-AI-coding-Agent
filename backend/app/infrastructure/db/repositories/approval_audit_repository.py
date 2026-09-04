from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.entities.human_approval import ApprovalAuditRecord
from app.infrastructure.db.models.approval import ApprovalAuditLogModel


class ApprovalAuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_approval_event(self, record: ApprovalAuditRecord) -> ApprovalAuditLogModel:
        model = ApprovalAuditLogModel(
            id=record.id,
            run_id=record.run_id,
            task_id=record.task_id,
            user_id=record.user_id,
            action=record.action.value if hasattr(record.action, 'value') else str(record.action),
            execution_mode=record.execution_mode.value if hasattr(record.execution_mode, 'value') else str(record.execution_mode),
            high_risk_flagged=record.high_risk_flagged,
            policy_triggers=record.policy_triggers,
            feedback_notes=record.feedback_notes,
            updated_requirements=record.updated_requirements,
            created_at=record.timestamp,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def get_audit_logs_for_run(self, run_id: str) -> List[ApprovalAuditLogModel]:
        stmt = select(ApprovalAuditLogModel).where(ApprovalAuditLogModel.run_id == run_id).order_by(ApprovalAuditLogModel.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
