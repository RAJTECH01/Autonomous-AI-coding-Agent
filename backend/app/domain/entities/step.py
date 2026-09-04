from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List


@dataclass
class ExecutionStep:
    id: str
    session_id: str
    step_number: int
    step_type: str  # thought, tool_call, reflection, code_review
    thought_process: Dict[str, Any] = field(default_factory=dict)
    input_context: Dict[str, Any] = field(default_factory=dict)
    output_summary: Dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    execution_time: Optional[datetime] = None


@dataclass
class ToolCallRecord:
    id: str
    step_id: str
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: Dict[str, Any]
    status: str  # success, error, timeout
    execution_duration_ms: int
    executed_at: Optional[datetime] = None
