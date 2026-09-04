import uuid
import pytest
from typing import List, Dict, Any, AsyncIterator, Optional

from app.domain.entities.agent import (
    AgentState,
    AgentLimits,
    AgentRun,
    AgentStep,
)
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage, LLMResponse
from app.domain.interfaces.sandbox import SandboxInterface, CommandResult
from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer
from app.infrastructure.tools.registry import ToolRegistry
from app.infrastructure.db.repositories.agent_repository import AgentRepository
from app.application.agent.state_machine import AgentStateMachine
from app.core.exceptions import ToolExecutionError, LimitExceededError
from app.infrastructure.db.models.user import UserModel
from app.infrastructure.db.models.project import ProjectModel
from app.infrastructure.db.models.task import CodingTaskModel
from tests.conftest import TestingSessionLocal


class MockAIProvider(AIProviderInterface):
    """Mock AI Provider for testing state machine execution without external API calls."""

    def __init__(self, responses: Optional[List[LLMResponse]] = None):
        self.responses = responses or []
        self.call_count = 0

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if self.responses and self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return LLMResponse(content="Analyzed and completed work.", tool_calls=[])

    async def stream_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        yield "Response stream"


class MockSandbox(SandboxInterface):
    """Mock Sandbox for testing command and test tool execution."""

    def __init__(self, test_should_pass: bool = True):
        self.test_should_pass = test_should_pass
        self.executed_commands: List[str] = []

    async def create_sandbox(self, session_id: str, workspace_path: str = ".") -> str:
        return "mock_sandbox_123"

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120) -> CommandResult:
        self.executed_commands.append(command)
        if "find" in command:
            return CommandResult(command=command, exit_code=0, stdout="./main.py\n./tests/test_main.py", stderr="", duration_ms=10)
        if "pytest" in command:
            if self.test_should_pass:
                return CommandResult(command=command, exit_code=0, stdout="2 passed in 0.1s", stderr="", duration_ms=50)
            else:
                return CommandResult(command=command, exit_code=1, stdout="1 failed, 1 passed", stderr="AssertionError: assert False", duration_ms=50)
        return CommandResult(command=command, exit_code=0, stdout="Command executed", stderr="", duration_ms=20)

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        return True

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        return "def hello(): pass"

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_agent_state_machine_successful_flow():
    """Verify clean state transition flow: RECEIVED -> ANALYZING -> PLANNING -> AWAITING_APPROVAL -> IMPLEMENTING -> TESTING -> REVIEWING -> COMPLETED."""
    provider = MockAIProvider([
        LLMResponse(content="Analysis: Need to create user entity."),
        LLMResponse(content="Plan: Step 1 create user.py"),
        LLMResponse(content="Implementation done.", tool_calls=[]),
        LLMResponse(content="Final review: Looks great!"),
    ])
    sandbox = MockSandbox(test_should_pass=True)

    async with TestingSessionLocal() as db:
        async with db.bind.begin() as conn:
            from app.infrastructure.db.models import Base
            await conn.run_sync(Base.metadata.create_all)

        user = UserModel(id=uuid.uuid4(), email="agenttest@example.com", password_hash="hash", full_name="Test User", role="user")
        project = ProjectModel(id=uuid.uuid4(), name="Test Project", slug="test-project", owner_id=user.id)
        task = CodingTaskModel(id=uuid.uuid4(), project_id=project.id, creator_id=user.id, title="Test Task", requirement_prompt="Create user service")
        db.add_all([user, project, task])
        await db.flush()

        task_id = str(task.id)
        repo = AgentRepository(db)
        agent = AgentStateMachine(
            task_id=task_id,
            user_prompt="Create user service",
            provider=provider,
            sandbox=sandbox,
            sandbox_id="sb_123",
            repository=repo,
            auto_approve=True,
        )

        result = await agent.run_autonomous_loop()
        await db.commit()

        assert result["status"] == AgentState.COMPLETED.value
        assert agent.run.state == AgentState.COMPLETED

        # Check recorded state history
        states_sequence = [step.to_state for step in agent.context.execution_history]
        expected_states = [
            AgentState.ANALYZING,
            AgentState.PLANNING,
            AgentState.AWAITING_APPROVAL,
            AgentState.IMPLEMENTING,
            AgentState.TESTING,
            AgentState.REVIEWING,
            AgentState.COMPLETED,
        ]
        assert states_sequence == expected_states


@pytest.mark.asyncio
async def test_agent_state_machine_pause_awaiting_approval():
    """Verify machine pauses at AWAITING_APPROVAL state when auto_approve=False."""
    task_id = str(uuid.uuid4())
    provider = MockAIProvider()
    sandbox = MockSandbox()

    agent = AgentStateMachine(
        task_id=task_id,
        user_prompt="Add payment gateway",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_123",
        auto_approve=False,
    )

    result = await agent.run_autonomous_loop()

    assert "AWAITING_APPROVAL" in result["status"]
    assert agent.run.state == AgentState.AWAITING_APPROVAL
    assert "AWAITING_APPROVAL" in result["message"]


@pytest.mark.asyncio
async def test_agent_state_machine_debug_and_retry_loop():
    """Verify state transition during test failures: TESTING -> DEBUGGING -> IMPLEMENTING -> TESTING -> REVIEWING -> COMPLETED."""
    task_id = str(uuid.uuid4())
    
    # Custom sandbox that fails first test run, then passes on second attempt
    class RetrySandbox(MockSandbox):
        def __init__(self):
            super().__init__()
            self.test_attempts = 0

        async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120) -> CommandResult:
            if "pytest" in command:
                self.test_attempts += 1
                if self.test_attempts == 1:
                    return CommandResult(command=command, exit_code=1, stdout="1 failed", stderr="SyntaxError", duration_ms=30)
                else:
                    return CommandResult(command=command, exit_code=0, stdout="1 passed", stderr="", duration_ms=30)
            return await super().execute_command(sandbox_id, command, timeout_seconds)

    sandbox = RetrySandbox()
    provider = MockAIProvider([
        LLMResponse(content="Analysis"),
        LLMResponse(content="Plan"),
        LLMResponse(content="Coding 1"),
        LLMResponse(content="Debug fix guidance"),
        LLMResponse(content="Coding fix applied"),
        LLMResponse(content="Final Review"),
    ])

    agent = AgentStateMachine(
        task_id=task_id,
        user_prompt="Fix bug in auth",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_123",
        auto_approve=True,
    )

    result = await agent.run_autonomous_loop()
    assert result["status"] == AgentState.COMPLETED.value, f"Run failed with error: {result.get('error')}"
    assert agent.run.test_attempts_count == 1

    states_sequence = [step.to_state for step in agent.context.execution_history]
    assert AgentState.DEBUGGING in states_sequence
    assert AgentState.TESTING in states_sequence


@pytest.mark.asyncio
async def test_controlled_tool_layer_security_and_limits():
    """Verify tool layer blocks forbidden commands and enforces limits."""
    tool_layer = ControlledToolLayer()

    # 1. Command safety check
    with pytest.raises(ToolExecutionError) as exc_info:
        tool_layer.validate_command_safety("run_command", {"command": "rm -rf /"})
    assert "Forbidden command pattern" in str(exc_info.value)

    # 2. Max tool calls limit check
    run = AgentRun(
        id=str(uuid.uuid4()),
        task_id=str(uuid.uuid4()),
        limits=AgentLimits(max_tool_calls=2),
        total_tool_calls=2,
    )
    sandbox = MockSandbox()

    with pytest.raises(LimitExceededError) as exc_info:
        await tool_layer.execute_tool(sandbox, "sb_123", "read_file", {"path": "main.py"}, run)
    assert "Maximum tool calls limit" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_state_machine_exceed_max_test_attempts():
    """Verify state machine transitions to FAILED when max test attempts limit is exceeded."""
    task_id = str(uuid.uuid4())
    provider = MockAIProvider()
    sandbox = MockSandbox(test_should_pass=False)  # Tests keep failing

    limits = AgentLimits(max_test_attempts=2)
    agent = AgentStateMachine(
        task_id=task_id,
        user_prompt="Fix breaking bug",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_123",
        limits=limits,
        auto_approve=True,
    )

    result = await agent.run_autonomous_loop()
    assert result["status"] == AgentState.FAILED.value
    assert agent.run.state == AgentState.FAILED
    assert "Max test attempts" in result["error"]


@pytest.mark.asyncio
async def test_agent_state_machine_review_feedback_loop():
    """Verify review feedback loop: REVIEWING -> IMPLEMENTING -> TESTING -> REVIEWING -> COMPLETED when review finds CRITICAL issues."""
    import json
    task_id = str(uuid.uuid4())

    review_fail_json = json.dumps({
        "passed": False,
        "summary": "Critical security issue found.",
        "findings": [
            {
                "finding": "Hardcoded secret key",
                "severity": "CRITICAL",
                "affected_file": "config.py",
                "explanation": "Secret key in source code",
                "recommended_fix": "Use env var",
                "category": "security"
            }
        ]
    })

    review_pass_json = json.dumps({
        "passed": True,
        "summary": "Code looks great and secure.",
        "findings": []
    })

    provider = MockAIProvider([
        LLMResponse(content="Analysis"),
        LLMResponse(content="Plan"),
        LLMResponse(content="Coding initial"),
        LLMResponse(content=review_fail_json),  # Review attempt 1 fails
        LLMResponse(content="Coding fix for review feedback"),
        LLMResponse(content=review_pass_json),  # Review attempt 2 passes
    ])

    sandbox = MockSandbox(test_should_pass=True)

    agent = AgentStateMachine(
        task_id=task_id,
        user_prompt="Build secure API",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_123",
        auto_approve=True,
    )

    result = await agent.run_autonomous_loop()

    assert result["status"] == AgentState.COMPLETED.value
    assert agent.run.state == AgentState.COMPLETED
    assert agent.run.review_attempts_count == 1

    states_sequence = [step.to_state for step in agent.context.execution_history]
    # Check that sequence includes REVIEWING -> IMPLEMENTING -> TESTING -> REVIEWING -> COMPLETED
    review_indices = [i for i, state in enumerate(states_sequence) if state == AgentState.REVIEWING]
    assert len(review_indices) == 2
    assert states_sequence[review_indices[0] + 1] == AgentState.IMPLEMENTING


@pytest.mark.asyncio
async def test_agent_state_machine_exceed_max_review_attempts():
    """Verify machine transitions to FAILED when max review attempts limit is reached."""
    import json
    task_id = str(uuid.uuid4())

    review_fail_json = json.dumps({
        "passed": False,
        "summary": "Unresolved critical flaw.",
        "findings": [
            {
                "finding": "Critical memory leak",
                "severity": "CRITICAL",
                "affected_file": "app.py",
                "explanation": "Unclosed handles",
                "recommended_fix": "Use context manager",
                "category": "correctness"
            }
        ]
    })

    provider = MockAIProvider([
        LLMResponse(content="Analysis"),
        LLMResponse(content="Plan"),
        LLMResponse(content="Coding 1"),
        LLMResponse(content=review_fail_json),
        LLMResponse(content="Coding 2"),
        LLMResponse(content=review_fail_json),
    ])

    sandbox = MockSandbox(test_should_pass=True)
    limits = AgentLimits(max_review_attempts=1)

    agent = AgentStateMachine(
        task_id=task_id,
        user_prompt="Fix memory leak",
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_123",
        limits=limits,
        auto_approve=True,
    )

    result = await agent.run_autonomous_loop()
    assert result["status"] == AgentState.FAILED.value
    assert agent.run.state == AgentState.FAILED
    assert "Review attempt limit reached" in result["error"] or "Max review attempts" in result["error"]

