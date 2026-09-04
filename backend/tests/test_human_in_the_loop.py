import pytest
import json
from typing import List, Dict, Any, Optional
from app.application.agent.state_machine import AgentStateMachine
from app.domain.entities.agent import AgentState
from app.domain.entities.human_approval import ExecutionMode, ApprovalAction
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage, LLMResponse
from app.domain.interfaces.sandbox import SandboxInterface, CommandResult


class MockHumanAIProvider(AIProviderInterface):
    def __init__(self, high_risk_plan: bool = False):
        self.high_risk_plan = high_risk_plan

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        user_msg = messages[-1].content
        if "Analyze" in user_msg or "Requirement" in user_msg:
            if self.high_risk_plan:
                return LLMResponse(content="Plan: Update security/auth.py and run pip install passlib", tool_calls=[])
            return LLMResponse(content="Plan: Create helper function in app/utils.py", tool_calls=[])
        return LLMResponse(content="Done", tool_calls=[])

    async def stream_response(self, messages, tools=None, model=None, temperature=0.2, max_tokens=4096):
        yield "Response"


class MockHumanSandbox(SandboxInterface):
    async def create_sandbox(self, session_id: str, workspace_path: str = ".") -> str:
        return "sb_100"
    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        return "content"
    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        return True
    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120) -> CommandResult:
        return CommandResult(command=command, exit_code=0, stdout="OK", stderr="", duration_ms=10)
    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_plan_only_execution_mode():
    provider = MockHumanAIProvider()
    sandbox = MockHumanSandbox()

    sm = AgentStateMachine(
        task_id="t-plan-only",
        user_prompt="Create utility helper function",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_100",
        execution_mode=ExecutionMode.PLAN_ONLY,
    )

    res = await sm.run_autonomous_loop()
    assert sm.run.state == AgentState.COMPLETED
    assert "PLAN_ONLY mode" in res["message"]


@pytest.mark.asyncio
async def test_approval_required_execution_mode_pauses():
    provider = MockHumanAIProvider()
    sandbox = MockHumanSandbox()

    sm = AgentStateMachine(
        task_id="t-app-req",
        user_prompt="Create utility helper function",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_100",
        execution_mode=ExecutionMode.APPROVAL_REQUIRED,
    )

    res = await sm.run_autonomous_loop()
    assert sm.run.state == AgentState.AWAITING_APPROVAL
    assert "AWAITING_APPROVAL" in res["status"]

    # Test User Approval Action
    await sm.handle_user_approval()
    assert sm.run.state == AgentState.IMPLEMENTING


@pytest.mark.asyncio
async def test_autonomous_mode_high_risk_override():
    # In AUTONOMOUS mode, if a high-risk action (e.g. auth change) is flagged, execution MUST pause for human approval!
    provider = MockHumanAIProvider(high_risk_plan=True)
    sandbox = MockHumanSandbox()

    sm = AgentStateMachine(
        task_id="t-auto-risk",
        user_prompt="Update auth token handling",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_100",
        execution_mode=ExecutionMode.AUTONOMOUS,
    )

    res = await sm.run_autonomous_loop()
    assert sm.run.state == AgentState.AWAITING_APPROVAL
    assert sm.run.high_risk_flagged is True


@pytest.mark.asyncio
async def test_user_rejection_loop():
    provider = MockHumanAIProvider()
    sandbox = MockHumanSandbox()

    sm = AgentStateMachine(
        task_id="t-reject",
        user_prompt="Create utility helper function",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_100",
        execution_mode=ExecutionMode.APPROVAL_REQUIRED,
    )

    await sm.run_autonomous_loop()
    assert sm.run.state == AgentState.AWAITING_APPROVAL

    # Reject plan with feedback
    await sm.handle_user_rejection(feedback_notes="Please use dataclasses instead of dicts.")
    assert sm.run.state == AgentState.PLANNING


@pytest.mark.asyncio
async def test_user_cancellation():
    provider = MockHumanAIProvider()
    sandbox = MockHumanSandbox()

    sm = AgentStateMachine(
        task_id="t-cancel",
        user_prompt="Create utility helper function",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_100",
        execution_mode=ExecutionMode.APPROVAL_REQUIRED,
    )

    await sm.run_autonomous_loop()
    await sm.handle_user_cancellation()
    assert sm.run.state == AgentState.CANCELLED


@pytest.mark.asyncio
async def test_modify_requirements():
    provider = MockHumanAIProvider()
    sandbox = MockHumanSandbox()

    sm = AgentStateMachine(
        task_id="t-modify",
        user_prompt="Initial requirement prompt",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_100",
        execution_mode=ExecutionMode.APPROVAL_REQUIRED,
    )

    await sm.run_autonomous_loop()
    await sm.handle_modify_requirements(new_requirement_prompt="Updated requirement prompt with extra constraints")
    assert sm.context.user_prompt == "Updated requirement prompt with extra constraints"
    assert sm.run.state == AgentState.ANALYZING
