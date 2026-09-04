import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, ForeignKey, Integer, Numeric, Text, Boolean, DateTime, UniqueConstraint, Index, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.db.base import Base, TimestampMixin, SoftDeleteMixin


class AgentRunModel(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coding_tasks.id", ondelete="CASCADE"), nullable=False)
    initiator_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    current_iteration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0.0, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["CodingTaskModel"] = relationship(back_populates="agent_runs")
    plans: Mapped[List["AgentPlanModel"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    steps: Mapped[List["AgentStepModel"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    code_versions: Mapped[List["CodeVersionModel"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    test_executions: Mapped[List["TestExecutionModel"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    error_logs: Mapped[List["ErrorLogModel"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_runs_task_status", "task_id", "status"),
        Index("idx_runs_initiator", "initiator_id", "created_at"),
    )


class AgentPlanModel(Base, TimestampMixin):
    __tablename__ = "agent_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    goals_summary: Mapped[str] = mapped_column(Text, nullable=False)
    plan_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    run: Mapped["AgentRunModel"] = relationship(back_populates="plans")


class AgentStepModel(Base, TimestampMixin):
    __tablename__ = "agent_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    thought_process: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    run: Mapped["AgentRunModel"] = relationship(back_populates="steps")
    tool_calls: Mapped[List["ToolCallModel"]] = relationship(back_populates="step", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("run_id", "step_number", name="uq_run_step_number"),
    )


class ToolCallModel(Base, TimestampMixin):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_input: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="success", nullable=False)
    execution_duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    step: Mapped["AgentStepModel"] = relationship(back_populates="tool_calls")
    result: Mapped[Optional["ToolResultModel"]] = relationship(back_populates="tool_call", uselist=False, cascade="all, delete-orphan")


class ToolResultModel(Base, TimestampMixin):
    __tablename__ = "tool_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_call_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tool_calls.id", ondelete="CASCADE"), nullable=False)
    stdout_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stderr_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_output_storage_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    exit_code: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    tool_call: Mapped["ToolCallModel"] = relationship(back_populates="result")


class CodeVersionModel(Base, TimestampMixin):
    __tablename__ = "code_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="SET NULL"), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    previous_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    new_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    diff_patch: Mapped[str] = mapped_column(Text, nullable=False)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    run: Mapped["AgentRunModel"] = relationship(back_populates="code_versions")


class TestExecutionModel(Base, TimestampMixin):
    __tablename__ = "test_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="SET NULL"), nullable=True)
    test_runner: Mapped[str] = mapped_column(String(50), nullable=False)
    total_tests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_tests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_output_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    run: Mapped["AgentRunModel"] = relationship(back_populates="test_executions")


class ErrorLogModel(Base, TimestampMixin):
    __tablename__ = "error_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="SET NULL"), nullable=True)
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    stack_trace: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="code_error", nullable=False)

    run: Mapped["AgentRunModel"] = relationship(back_populates="error_logs")
    fixes: Mapped[List["CodeFixModel"]] = relationship(back_populates="error_log", cascade="all, delete-orphan")


class CodeFixModel(Base, TimestampMixin):
    __tablename__ = "code_fixes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    error_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("error_logs.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    root_cause_analysis: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_fix: Mapped[str] = mapped_column(Text, nullable=False)
    files_modified: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    was_successful: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    error_log: Mapped["ErrorLogModel"] = relationship(back_populates="fixes")
