from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum


class ExecutionMode(str, Enum):
    PLAN_ONLY = "PLAN_ONLY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    AUTONOMOUS = "AUTONOMOUS"


class ApprovalAction(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    MODIFY_REQUIREMENTS = "MODIFY_REQUIREMENTS"


class HighRiskCategory(str, Enum):
    DELETE_MANY_FILES = "DELETE_MANY_FILES"
    CHANGE_AUTH = "CHANGE_AUTH"
    MODIFY_PROD_CONFIG = "MODIFY_PROD_CONFIG"
    CHANGE_DB_SCHEMA = "CHANGE_DB_SCHEMA"
    INSTALL_DEPENDENCIES = "INSTALL_DEPENDENCIES"
    ENABLE_NETWORK_ACCESS = "ENABLE_NETWORK_ACCESS"
    EXECUTE_PRIVILEGED_OP = "EXECUTE_PRIVILEGED_OP"


@dataclass
class HighRiskEvaluationResult:
    is_high_risk: bool = False
    flagged_categories: List[HighRiskCategory] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)
    flagged_files: List[str] = field(default_factory=list)
    flagged_commands: List[str] = field(default_factory=list)


@dataclass
class ApprovalAuditRecord:
    id: str
    run_id: str
    task_id: str
    user_id: Optional[str]
    action: ApprovalAction
    execution_mode: ExecutionMode
    high_risk_flagged: bool = False
    policy_triggers: List[str] = field(default_factory=list)
    feedback_notes: Optional[str] = None
    updated_requirements: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
