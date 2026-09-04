from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ToolPermission(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    ADMIN = "ADMIN"


class ToolExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DENIED = "DENIED"
    TIMEOUT = "TIMEOUT"


class ToolMetadata(BaseModel):
    name: str
    description: str
    permission_required: ToolPermission
    timeout_seconds: int = 30
    max_output_chars: int = 50000


class ToolAuditRecord(BaseModel):
    id: str
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    agent_run_id: Optional[str] = None
    tool_name: str
    permission_required: ToolPermission
    status: ToolExecutionStatus
    input_metadata: Dict[str, Any] = Field(default_factory=dict)
    output_metadata: Dict[str, Any] = Field(default_factory=dict)
    error_metadata: Optional[Dict[str, Any]] = None
    execution_duration_ms: int = 0
    start_time: datetime
    end_time: datetime


SENSITIVE_KEY_SUBSTRINGS = {
    "password", "secret", "token", "api_key", "apikey", "auth",
    "private_key", "credential", "access_key", "jwt"
}


def mask_sensitive_data(data: Any) -> Any:
    """
    Recursively scrub sensitive keys (passwords, tokens, API keys, secrets)
    from dictionary structures to prevent leakages in audit logs.
    """
    if isinstance(data, dict):
        masked_dict = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_KEY_SUBSTRINGS):
                masked_dict[key] = "********"
            else:
                masked_dict[key] = mask_sensitive_data(value)
        return masked_dict
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data
