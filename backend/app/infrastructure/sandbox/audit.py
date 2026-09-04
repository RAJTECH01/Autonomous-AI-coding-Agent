from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.core.logging import logger


class SandboxAuditEventType(str, Enum):
    SANDBOX_CREATED = "SANDBOX_CREATED"
    COMMAND_EXECUTED = "COMMAND_EXECUTED"
    FILE_READ = "FILE_READ"
    FILE_WRITTEN = "FILE_WRITTEN"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    TIMEOUT_EXCEEDED = "TIMEOUT_EXCEEDED"
    SANDBOX_DESTROYED = "SANDBOX_DESTROYED"


class SandboxAuditRecord(BaseModel):
    event_id: str
    event_type: SandboxAuditEventType
    sandbox_id: str
    session_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    command: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    file_path: Optional[str] = None
    output_truncated: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class SandboxAuditLogger:
    """
    Audit log engine recording all sandbox lifecycle operations, commands,
    resource limits, output truncation events, and security violations.
    """

    def __init__(self):
        self._audit_trail: List[SandboxAuditRecord] = []

    def record_event(self, record: SandboxAuditRecord):
        self._audit_trail.append(record)
        logger.info(
            "Sandbox audit record logged",
            event_type=record.event_type,
            sandbox_id=record.sandbox_id,
            session_id=record.session_id,
            command=record.command,
            exit_code=record.exit_code,
            duration_ms=record.duration_ms,
        )

    def get_records_for_sandbox(self, sandbox_id: str) -> List[SandboxAuditRecord]:
        return [r for r in self._audit_trail if r.sandbox_id == sandbox_id]

    def get_all_records(self) -> List[SandboxAuditRecord]:
        return list(self._audit_trail)


# Global audit logger instance
audit_logger = SandboxAuditLogger()
