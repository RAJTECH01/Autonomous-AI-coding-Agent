import json
import pytest
from typing import Dict, Any, List, Optional
from app.domain.entities.debugging_agent import (
    DebugInputContext,
    ValidationComparison,
    StructuredDebugResult,
)
from app.domain.entities.testing_agent import StructuredTestResult, FailingTestDetail
from app.application.agent.subagents.debugger import DebuggingAgent
from app.application.agent.subagents.coder import CodingAgent
from app.application.agent.subagents.tester import TestingValidationAgent
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage, LLMResponse
from app.domain.interfaces.sandbox import SandboxInterface, CommandResult


class MockDebugAIProvider(AIProviderInterface):
    """Mock AI Provider for DebuggingAgent testing."""
    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        user_msg = messages[-1].content
        if "Analyze the following software failure context" in user_msg:
            json_payload = {
                "root_cause": "KeyError 'user_id' in app/services/auth.py:45 due to missing session payload mapping",
                "affected_files": ["app/services/auth.py"],
                "proposed_fix": "Extract user_id from token payload before session initialization",
                "confidence": 0.95
            }
            return LLMResponse(content=f"```json\n{json.dumps(json_payload)}\n```", tool_calls=[])
        
        if "File to fix:" in user_msg:
            fixed_code = "def authenticate():\n    # Fixed user_id extraction\n    return {'user_id': 123, 'status': 'ok'}\n"
            return LLMResponse(content=fixed_code, tool_calls=[])

        return LLMResponse(content="Analysis complete.", tool_calls=[])

    async def stream_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        yield "Response stream"


class MockDebugSandbox(SandboxInterface):
    """Mock sandbox storing files and test execution results."""
    def __init__(self, test_passes_after_fix: bool = True):
        self.test_passes_after_fix = test_passes_after_fix
        self.files: Dict[str, str] = {
            "app/services/auth.py": "def authenticate():\n    return {'status': 'ok'}\n"
        }
        self.execution_attempts = 0

    async def create_sandbox(self, session_id: str, workspace_path: str = ".") -> str:
        return "sb_debug_789"

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        if file_path in self.files:
            return self.files[file_path]
        raise FileNotFoundError(f"File '{file_path}' not found.")

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        self.files[file_path] = content
        return True

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120) -> CommandResult:
        if "find" in command:
            return CommandResult(command=command, exit_code=0, stdout="./app/services/auth.py\n./tests/test_auth.py", stderr="", duration_ms=10)
        
        if "pytest" in command:
            self.execution_attempts += 1
            if self.test_passes_after_fix and self.execution_attempts > 1:
                return CommandResult(command=command, exit_code=0, stdout="2 passed in 0.04s", stderr="", duration_ms=20)
            else:
                stdout = "FAILED tests/test_auth.py::test_login - KeyError: 'user_id'\n== 1 failed in 0.04s =="
                return CommandResult(command=command, exit_code=1, stdout=stdout, stderr="KeyError", duration_ms=20)

        return CommandResult(command=command, exit_code=0, stdout="Done", stderr="", duration_ms=10)

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_debugging_agent_full_7step_flow():
    """Verify full 7-step debugging protocol and structured debug output."""
    provider = MockDebugAIProvider()
    sandbox = MockDebugSandbox(test_passes_after_fix=True)

    coder = CodingAgent(provider=provider, sandbox=sandbox, sandbox_id="sb_1")
    tester = TestingValidationAgent(sandbox=sandbox, sandbox_id="sb_1", provider=provider)
    debugger = DebuggingAgent(provider=provider, sandbox=sandbox, sandbox_id="sb_1", coder=coder, tester=tester)

    context = DebugInputContext(
        requirement="Fix login authentication payload key error",
        implementation_plan="1. Fix auth service token parsing",
        changed_files=["app/services/auth.py"],
        test_results="FAILED tests/test_auth.py::test_login - KeyError: 'user_id'",
        runtime_errors="KeyError: 'user_id'",
        logs="Traceback at line 45 in auth.py",
    )

    result: StructuredDebugResult = await debugger.execute_debugging_flow(context)

    assert result.root_cause != ""
    assert "user_id" in result.root_cause
    assert result.affected_files == ["app/services/auth.py"]
    assert result.proposed_fix != ""
    assert len(result.applied_changes) == 1
    assert result.applied_changes[0]["file_path"] == "app/services/auth.py"
    assert result.confidence == 0.95
    assert result.loop_detected is False

    # Verify validation comparison
    val: ValidationComparison = result.validation_result
    assert val.passed is True
    assert val.previous_failed_count == 1
    assert val.current_failed_count == 0
    assert val.tests_fixed_count == 1
    assert "SUCCESS" in val.delta_summary

    # Verify file content was actually updated in sandbox
    assert "Fixed user_id extraction" in sandbox.files["app/services/auth.py"]


@pytest.mark.asyncio
async def test_debugging_agent_infinite_loop_detection():
    """Verify DebuggingAgent detects infinite failure loops and halts retries."""
    provider = MockDebugAIProvider()
    sandbox = MockDebugSandbox(test_passes_after_fix=False)  # Tests keep failing with same error

    debugger = DebuggingAgent(
        provider=provider,
        sandbox=sandbox,
        sandbox_id="sb_1",
        max_debug_loops=3,
    )

    context = DebugInputContext(
        requirement="Fix recurring bug",
        changed_files=["app/services/auth.py"],
        runtime_errors="Persistent KeyError: 'user_id'",
    )

    # Run loop 1
    res1 = await debugger.execute_debugging_flow(context)
    assert res1.loop_detected is False

    # Run loop 2
    res2 = await debugger.execute_debugging_flow(context)
    assert res2.loop_detected is False

    # Run loop 3 -> Loop count triggers max limit
    res3 = await debugger.execute_debugging_flow(context)
    assert res3.loop_detected is True
    assert "Infinite Debug Loop Detected" in res3.root_cause
    assert res3.validation_result.passed is False


@pytest.mark.asyncio
async def test_debugging_agent_unrelated_functionality_protection():
    """Verify DebuggingAgent restricts edits strictly to affected files."""
    provider = MockDebugAIProvider()
    sandbox = MockDebugSandbox(test_passes_after_fix=True)
    sandbox.files["app/services/unrelated.py"] = "def unrelated_func(): pass\n"

    coder = CodingAgent(provider=provider, sandbox=sandbox, sandbox_id="sb_1")
    debugger = DebuggingAgent(provider=provider, sandbox=sandbox, sandbox_id="sb_1", coder=coder)

    context = DebugInputContext(
        requirement="Fix auth bug",
        changed_files=["app/services/auth.py"],
        runtime_errors="KeyError in auth.py",
    )

    result = await debugger.execute_debugging_flow(context)
    assert "app/services/unrelated.py" not in result.affected_files
    assert sandbox.files["app/services/unrelated.py"] == "def unrelated_func(): pass\n"
