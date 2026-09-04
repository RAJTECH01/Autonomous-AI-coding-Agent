import pytest
from typing import Dict, Any, List, Optional
from app.domain.entities.testing_agent import (
    FailingTestDetail,
    ParsedTestOutput,
    TestResourceLimits,
    StructuredTestResult,
)
from app.application.agent.testing.test_adapters import (
    PytestAdapter,
    JestAdapter,
    TestRunnerRegistry,
)
from app.application.agent.subagents.tester import TestingValidationAgent
from app.domain.interfaces.sandbox import SandboxInterface, CommandResult


class MockTestingSandbox(SandboxInterface):
    """Mock sandbox simulating workspace files and test execution output."""

    def __init__(self, targeted_pass: bool = True, broader_pass: bool = True, custom_stdout: Optional[str] = None):
        self.targeted_pass = targeted_pass
        self.broader_pass = broader_pass
        self.custom_stdout = custom_stdout
        self.executed_commands: List[str] = []

    async def create_sandbox(self, session_id: str, workspace_path: str = ".") -> str:
        return "sb_test_456"

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        return "def test_example(): pass"

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        return True

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120) -> CommandResult:
        self.executed_commands.append(command)

        if "find" in command:
            # Return workspace file listing
            files = [
                "./app/services/auth_service.py",
                "./tests/test_auth_service.py",
                "./tests/test_main.py",
                "./pytest.ini",
            ]
            return CommandResult(command=command, exit_code=0, stdout="\n".join(files), stderr="", duration_ms=15)

        if "pytest" in command:
            if self.custom_stdout:
                exit_code = 0 if self.targeted_pass else 1
                return CommandResult(command=command, exit_code=exit_code, stdout=self.custom_stdout, stderr="", duration_ms=50)

            # Check if command targets specific test file or full suite
            if "tests/test_auth_service.py" in command or "test_auth" in command:
                if self.targeted_pass:
                    stdout = "tests/test_auth_service.py::test_login PASSED\n\n== 2 passed in 0.05s =="
                    return CommandResult(command=command, exit_code=0, stdout=stdout, stderr="", duration_ms=40)
                else:
                    stdout = (
                        "FAILED tests/test_auth_service.py::test_login - AssertionError: assert 401 == 200\n"
                        "tests/test_auth_service.py:45: AssertionError\n"
                        "== 1 failed, 1 passed in 0.05s =="
                    )
                    return CommandResult(command=command, exit_code=1, stdout=stdout, stderr="AssertionError", duration_ms=40)
            else:
                if self.broader_pass:
                    stdout = "tests/test_main.py PASSED\n== 5 passed in 0.10s =="
                    return CommandResult(command=command, exit_code=0, stdout=stdout, stderr="", duration_ms=80)
                else:
                    stdout = "FAILED tests/test_main.py::test_health - KeyError: 'status'\n== 1 failed in 0.10s =="
                    return CommandResult(command=command, exit_code=1, stdout=stdout, stderr="KeyError", duration_ms=80)

        return CommandResult(command=command, exit_code=0, stdout="Done", stderr="", duration_ms=10)

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_pytest_adapter_detection_and_targeting():
    """Verify PytestAdapter detects python test projects and identifies targeted tests."""
    adapter = PytestAdapter()
    workspace_files = [
        "app/services/user_service.py",
        "tests/test_user_service.py",
        "pytest.ini",
    ]

    assert adapter.detect(workspace_files) is True
    assert adapter.framework_name == "pytest"
    assert adapter.language == "python"

    targeted = adapter.identify_targeted_tests(["app/services/user_service.py"], workspace_files)
    assert targeted == ["tests/test_user_service.py"]


@pytest.mark.asyncio
async def test_jest_adapter_detection():
    """Verify JestAdapter detection for JavaScript/TypeScript projects."""
    adapter = JestAdapter()
    assert adapter.detect(["jest.config.js", "src/index.ts"]) is True
    assert adapter.framework_name == "jest"
    assert adapter.language == "javascript"


@pytest.mark.asyncio
async def test_pytest_output_parsing_and_cause_classification():
    """Verify framework output parsing extracts failing test names, line numbers, and likely causes."""
    adapter = PytestAdapter()
    sample_output = (
        "FAILED tests/test_auth.py::test_login_failure - KeyError: 'user_id'\n"
        "tests/test_auth.py:42: KeyError\n"
        "FAILED tests/test_db.py::test_connect - AssertionError: assert None is not None\n"
        "== 2 failed, 3 passed in 0.25s =="
    )

    parsed = adapter.parse_output(exit_code=1, stdout=sample_output, stderr="")
    assert parsed.passed is False
    assert parsed.passed_count == 3
    assert parsed.failed_count == 2
    assert parsed.total_count == 5

    assert len(parsed.failing_tests) == 2
    assert parsed.failing_tests[0].test_name == "tests/test_auth.py::test_login_failure"
    assert parsed.failing_tests[0].file_path == "tests/test_auth.py"
    assert "KeyError" in parsed.failing_tests[0].likely_cause

    assert "KeyError: Missing expected dictionary key or payload attribute" in parsed.likely_causes
    assert "Assertion Failure: Value did not match expectation" in parsed.likely_causes


@pytest.mark.asyncio
async def test_prevention_of_false_positives_zero_tests():
    """Verify system rejects 'command exited successfully with 0 tests' as proof of correctness."""
    adapter = PytestAdapter()
    output_zero_tests = "collected 0 items\n\n== 0 passed in 0.01s =="

    parsed = adapter.parse_output(exit_code=0, stdout=output_zero_tests, stderr="")
    assert parsed.passed is False  # Reject 0 tests ran as proof of success
    assert parsed.total_count == 0


@pytest.mark.asyncio
async def test_testing_validation_agent_targeted_first_success():
    """Verify targeted tests run first, followed by broader test suite on success."""
    sandbox = MockTestingSandbox(targeted_pass=True, broader_pass=True)
    agent = TestingValidationAgent(sandbox=sandbox, sandbox_id="sb_1")

    result: StructuredTestResult = await agent.run_testing_pipeline(
        modified_files=["app/services/auth_service.py"]
    )

    assert result.passed is True
    assert result.framework == "pytest"
    assert result.targeted_tests_run == ["./tests/test_auth_service.py"]
    assert len(result.broader_tests_run) == 1
    assert result.passed_count > 0
    assert result.failed_count == 0

    # Assert execution order: targeted command ran BEFORE broader command
    cmds = sandbox.executed_commands
    pytest_cmds = [c for c in cmds if "pytest" in c]
    assert len(pytest_cmds) == 2
    assert "tests/test_auth_service.py" in pytest_cmds[0]
    assert pytest_cmds[1] == "pytest -v"


@pytest.mark.asyncio
async def test_testing_validation_agent_targeted_failure_halts_pipeline():
    """Verify pipeline halts immediately if targeted tests fail, returning structured error."""
    sandbox = MockTestingSandbox(targeted_pass=False, broader_pass=True)
    agent = TestingValidationAgent(sandbox=sandbox, sandbox_id="sb_1")

    result: StructuredTestResult = await agent.run_testing_pipeline(
        modified_files=["app/services/auth_service.py"]
    )

    assert result.passed is False
    assert result.targeted_tests_run == ["./tests/test_auth_service.py"]
    assert result.broader_tests_run == []  # Broader tests were NOT run!
    assert len(result.failing_tests) >= 1
    assert "AssertionError" in result.failing_tests[0].failure_message

    # Verify only targeted test command was executed
    cmds = [c for c in sandbox.executed_commands if "pytest" in c]
    assert len(cmds) == 1
    assert "tests/test_auth_service.py" in cmds[0]


@pytest.mark.asyncio
async def test_testing_validation_agent_output_truncation():
    """Verify output limits truncate large stdout/stderr outputs."""
    huge_stdout = "x" * 100_000
    sandbox = MockTestingSandbox(targeted_pass=True, custom_stdout=huge_stdout)
    limits = TestResourceLimits(max_output_chars=1000)
    agent = TestingValidationAgent(sandbox=sandbox, sandbox_id="sb_1", limits=limits)

    result = await agent.run_testing_pipeline(custom_test_path="tests/test_main.py")
    assert len(result.stdout) <= 2000  # Truncated within limit boundaries
