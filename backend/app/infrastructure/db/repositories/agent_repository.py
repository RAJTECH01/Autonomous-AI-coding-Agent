import uuid
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.repositories.base import BaseRepository
from app.infrastructure.db.models.agent import (
    AgentRunModel,
    AgentPlanModel,
    AgentStepModel,
    ToolCallModel,
    ToolResultModel,
    ErrorLogModel,
)
from app.domain.entities.agent import AgentRun, AgentStep, AgentPlan, ToolCall, ToolResult, AgentError


class AgentRepository(BaseRepository[AgentRunModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(AgentRunModel, session)

    async def create_run(self, run: AgentRun) -> AgentRunModel:
        model = AgentRunModel(
            id=uuid.UUID(run.id),
            task_id=uuid.UUID(run.task_id),
            initiator_id=uuid.UUID(run.initiator_id) if run.initiator_id else None,
            status=run.state.value,
            provider_name=run.provider_name,
            model_name=run.model_name,
            max_iterations=run.limits.max_iterations,
            current_iteration=run.current_iteration,
            total_tokens_used=run.total_tokens_used,
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
            estimated_cost_usd=run.estimated_cost_usd,
            started_at=run.started_at or datetime.now(timezone.utc),
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def update_run_state(self, run: AgentRun) -> None:
        stmt = select(AgentRunModel).where(AgentRunModel.id == uuid.UUID(run.id))
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if model:
            model.status = run.state.value
            model.current_iteration = run.current_iteration
            model.total_tokens_used = run.total_tokens_used
            model.prompt_tokens = run.prompt_tokens
            model.completion_tokens = run.completion_tokens
            model.estimated_cost_usd = run.estimated_cost_usd
            if run.completed_at:
                model.completed_at = run.completed_at
            await self.session.flush()

    async def create_plan(self, plan: AgentPlan) -> AgentPlanModel:
        model = AgentPlanModel(
            id=uuid.UUID(plan.id),
            run_id=uuid.UUID(plan.run_id),
            version=plan.version,
            goals_summary=plan.goals_summary,
            plan_markdown=plan.plan_markdown,
            status=plan.status,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def create_step(self, step: AgentStep) -> AgentStepModel:
        model = AgentStepModel(
            id=uuid.UUID(step.id),
            run_id=uuid.UUID(step.run_id),
            step_number=step.step_number,
            step_type=step.step_type,
            thought_process={
                "from_state": step.from_state.value,
                "to_state": step.to_state.value,
                **step.thought_process,
            },
            tokens_used=step.tokens_used,
            duration_ms=step.duration_ms,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def create_tool_call_and_result(
        self, tool_call: ToolCall, tool_result: ToolResult
    ) -> ToolCallModel:
        call_model = ToolCallModel(
            id=uuid.UUID(tool_call.id),
            step_id=uuid.UUID(tool_call.step_id) if tool_call.step_id else uuid.uuid4(),
            tool_name=tool_call.tool_name,
            tool_input=tool_call.tool_input,
            status="success" if tool_result.success else "failed",
            execution_duration_ms=tool_result.execution_duration_ms,
        )
        self.session.add(call_model)
        await self.session.flush()

        result_model = ToolResultModel(
            id=uuid.UUID(tool_result.id),
            tool_call_id=call_model.id,
            stdout_summary=tool_result.stdout_summary,
            stderr_summary=tool_result.stderr_summary,
            exit_code=tool_result.exit_code,
            raw_output_storage_url=tool_result.raw_output_storage_url,
        )
        self.session.add(result_model)
        await self.session.flush()
        return call_model

    async def create_error(self, error: AgentError) -> ErrorLogModel:
        model = ErrorLogModel(
            id=uuid.UUID(error.id),
            run_id=uuid.UUID(error.run_id),
            step_id=uuid.UUID(error.step_id) if error.step_id else None,
            error_type=error.error_type,
            stack_trace=error.stack_trace,
            category=error.category,
        )
        self.session.add(model)
        await self.session.flush()
        return model
