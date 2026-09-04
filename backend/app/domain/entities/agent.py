from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class AgentState(str, Enum):
    RECEIVED = "RECEIVED"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    DEBUGGING = "DEBUGGING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class AgentLimits:
    max_iterations: int = 20
    max_execution_time: float = 300.0  # seconds
    max_tool_calls: int = 50
    max_files_changed: int = 20
    max_generated_output: int = 100_000  # characters/bytes
    max_test_attempts: int = 5
    max_review_attempts: int = 3


@dataclass
class ToolCall:
    id: str
    tool_name: str
    tool_input: Dict[str, Any]
    step_id: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class ToolResult:
    id: str
    tool_call_id: str
    stdout_summary: Optional[str] = None
    stderr_summary: Optional[str] = None
    exit_code: int = 0
    execution_duration_ms: int = 0
    raw_output_storage_url: Optional[str] = None
    success: bool = True
    output: str = ""
    error: Optional[str] = None


@dataclass
class AgentDecision:
    next_state: AgentState
    thought_process: Dict[str, Any] = field(default_factory=dict)
    proposed_tool_calls: List[ToolCall] = field(default_factory=list)
    plan_update: Optional[str] = None
    code_changes: List[Dict[str, Any]] = field(default_factory=list)
    review_notes: Optional[str] = None


@dataclass
class AgentError:
    id: str
    run_id: str
    error_type: str
    stack_trace: str
    category: str = "code_error"  # code_error, tool_error, limit_exceeded, timeout, system_error
    step_id: Optional[str] = None
    root_cause: Optional[str] = None
    proposed_fix: Optional[str] = None


@dataclass
class AgentPlan:
    id: str
    run_id: str
    goals_summary: str
    plan_markdown: str
    version: int = 1
    status: str = "active"
    created_at: Optional[datetime] = None


@dataclass
class AgentStep:
    id: str
    run_id: str
    step_number: int
    from_state: AgentState
    to_state: AgentState
    step_type: str  # analysis, planning, tool_execution, debugging, review
    thought_process: Dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    duration_ms: int = 0
    tool_calls: List[ToolCall] = field(default_factory=list)
    created_at: Optional[datetime] = None


@dataclass
class AgentContext:
    user_prompt: str
    project_id: str
    task_id: str
    workspace_root: str = "."
    inspected_files: List[str] = field(default_factory=list)
    file_contents: Dict[str, str] = field(default_factory=dict)
    memory_messages: List[Dict[str, Any]] = field(default_factory=list)
    active_plan: Optional[AgentPlan] = None
    execution_history: List[AgentStep] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)


from app.domain.entities.human_approval import ExecutionMode


@dataclass
class AgentRun:
    id: str
    task_id: str
    state: AgentState = AgentState.RECEIVED
    execution_mode: ExecutionMode = ExecutionMode.APPROVAL_REQUIRED
    high_risk_flagged: bool = False
    high_risk_triggers: List[str] = field(default_factory=list)
    # Set by an authenticated human approval; consulted before high-risk tool calls.
    high_risk_approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    approved_plan_hash: Optional[str] = None
    initiator_id: Optional[str] = None
    provider_name: str = "anthropic"
    model_name: str = "claude-3-5-sonnet-20241022"
    limits: AgentLimits = field(default_factory=AgentLimits)
    current_iteration: int = 0
    total_tool_calls: int = 0
    files_changed_count: int = 0
    test_attempts_count: int = 0
    review_attempts_count: int = 0
    total_output_chars: int = 0
    total_tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_summary: Dict[str, Any] = field(default_factory=dict)
