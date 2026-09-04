import pytest
from typing import Dict, Any, List, Optional
from app.domain.entities.coding_agent import (
    FileVersionSnapshot,
    FileChangeRecord,
    StructuredFailureReport,
    SafeguardViolationError,
)
from app.application.agent.safeguards import CodingSafeguardManager
from app.application.agent.subagents.coder import CodingAgent
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage, LLMResponse
from app.domain.interfaces.sandbox import SandboxInterface, CommandResult


class MockAIProvider(AIProviderInterface):
    """Mock AI Provider for testing CodingAgent."""
    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return LLMResponse(content="Code generated cleanly.", tool_calls=[])

    async def stream_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        yield "Response stream"


class InMemorySandbox(SandboxInterface):
    """In-memory mock sandbox storing file contents and command results."""
    def __init__(self, test_should_pass: bool = True):
        self.files: Dict[str, str] = {}
        self.test_should_pass = test_should_pass
        self.commands_run: List[str] = []

    async def create_sandbox(self, session_id: str, workspace_path: str = ".") -> str:
        return "sb_test_123"

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        if file_path in self.files:
            return self.files[file_path]
        raise FileNotFoundError(f"File '{file_path}' not found.")

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        self.files[file_path] = content
        return True

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120) -> CommandResult:
        self.commands_run.append(command)
        if "rm" in command:
            target = command.replace("rm", "").replace("'", "").strip()
            self.files.pop(target, None)
            return CommandResult(command=command, exit_code=0, stdout="Deleted", stderr="", duration_ms=10)
        if "pytest" in command:
            if self.test_should_pass:
                return CommandResult(command=command, exit_code=0, stdout="3 passed in 0.05s", stderr="", duration_ms=20)
            else:
                return CommandResult(command=command, exit_code=1, stdout="1 failed", stderr="AssertionError: assert 1 == 2", duration_ms=20)
        return CommandResult(command=command, exit_code=0, stdout="Done", stderr="", duration_ms=10)

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_coding_agent_7step_file_modification_protocol():
    """Verify 7-step protocol: read -> understand -> minimal diff -> validate -> snapshot -> write -> test."""
    provider = MockAIProvider()
    sandbox = InMemorySandbox(test_should_pass=True)
    # Pre-populate file
    await sandbox.write_file("sb_1", "app/main.py", "def add(a, b):\n    return a + b\n")

    coder = CodingAgent(provider=provider, sandbox=sandbox, sandbox_id="sb_1")

    # Step 1-7 execution: Modify main.py
    new_code = "def add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n    return a + b\n"
    res = await coder.modify_file_safely(
        file_path="app/main.py",
        proposed_content_or_patch=new_code,
        reason="Add docstring to add function",
        related_requirement="REQ-101: Document math utils",
        related_test="tests/test_main.py",
    )

    assert res["success"] is True
    assert res["file_path"] == "app/main.py"
    assert res["snapshot_id"] is not None
    assert "add" in res["structure_summary"]["functions"]
    assert "app/main.py" in coder.get_files_changed()

    # Verify snapshot was stored
    assert len(coder.snapshots) == 1
    assert coder.snapshots[0].file_path == "app/main.py"
    assert "def add(a, b):" in coder.snapshots[0].content

    # Verify metadata tracking
    records = coder.get_change_history()
    assert len(records) == 1
    assert records[0]["file_path"] == "app/main.py"
    assert records[0]["reason"] == "Add docstring to add function"
    assert records[0]["related_requirement"] == "REQ-101: Document math utils"
    assert records[0]["related_test"] == "tests/test_main.py"
    assert records[0]["previous_version_metadata"] is not None


@pytest.mark.asyncio
async def test_coding_agent_syntax_validation_failure():
    """Verify Step 5 rejects invalid Python code before writing to file."""
    provider = MockAIProvider()
    sandbox = InMemorySandbox()
    coder = CodingAgent(provider=provider, sandbox=sandbox, sandbox_id="sb_1")

    invalid_python = "def broken_syntax(:\n    pass"

    with pytest.raises(ValueError) as exc_info:
        await coder.modify_file_safely(
            file_path="app/broken.py",
            proposed_content_or_patch=invalid_python,
            reason="Create function with broken syntax",
            related_requirement="REQ-102",
        )

    assert "Syntax Validation Failed" in str(exc_info.value)
    assert "app/broken.py" not in sandbox.files


@pytest.mark.asyncio
async def test_safeguard_accidental_deletion():
    """Verify Accidental Deletion Safeguard blocks deletion of critical files like requirements.txt or .git."""
    mgr = CodingSafeguardManager()

    with pytest.raises(SafeguardViolationError) as exc_info:
        mgr.check_deletion_safeguard("requirements.txt")
    assert "protected critical project file" in str(exc_info.value)

    with pytest.raises(SafeguardViolationError) as exc_info:
        mgr.check_deletion_safeguard(".git")
    assert "protected critical project file" in str(exc_info.value)


@pytest.mark.asyncio
async def test_safeguard_unrelated_file_modification():
    """Verify Unrelated File Modification Safeguard restricts edits outside approved target scope."""
    mgr = CodingSafeguardManager(allowed_target_files=["app/services/user.py"])

    # Path traversal check
    with pytest.raises(SafeguardViolationError) as exc_info:
        mgr.check_file_scope_safeguard("../outside_project.py")
    assert "Unrelated File Modification Blocked" in str(exc_info.value)

    # Allowed target scope check
    with pytest.raises(SafeguardViolationError) as exc_info:
        mgr.check_file_scope_safeguard("app/services/other.py")
    assert "is not in the approved plan targets" in str(exc_info.value)

    # Approved target should pass
    mgr.check_file_scope_safeguard("app/services/user.py")


@pytest.mark.asyncio
async def test_safeguard_huge_generated_files():
    """Verify Huge Generated Files Safeguard blocks oversized outputs or excessive line expansions."""
    mgr = CodingSafeguardManager(max_file_lines=100, max_file_bytes=5000)

    # 1. Line count limit
    huge_code = "\n".join([f"# line {i}" for i in range(150)])
    with pytest.raises(SafeguardViolationError) as exc_info:
        mgr.check_file_size_safeguard("app/huge.py", huge_code)
    assert "150 lines" in str(exc_info.value)

    # 2. Excessive expansion check
    mgr2 = CodingSafeguardManager(max_file_lines=1000, max_file_bytes=50000)
    old_code = "\n".join([f"# line {i}" for i in range(30)])
    expanded_code = "\n".join([f"# line {i}" for i in range(500)])
    with pytest.raises(SafeguardViolationError) as exc_info:
        mgr2.check_file_size_safeguard("app/huge.py", expanded_code, existing_content=old_code)
    assert "expanded excessively" in str(exc_info.value)


@pytest.mark.asyncio
async def test_safeguard_infinite_modification_loops():
    """Verify Infinite Loop Safeguard detects when a file is modified repeatedly without progress."""
    mgr = CodingSafeguardManager(max_modifications_per_file=3)
    file_path = "app/loop.py"

    mgr.file_modification_counts[file_path] = 3

    with pytest.raises(SafeguardViolationError) as exc_info:
        mgr.check_infinite_loop_safeguard(file_path)
    assert "modified 3 times in this run" in str(exc_info.value)


@pytest.mark.asyncio
async def test_safeguard_repeated_identical_fixes():
    """Verify Repeated Identical Fix Safeguard blocks re-applying a failed patch fingerprint."""
    mgr = CodingSafeguardManager()
    file_path = "app/bug.py"
    failed_patch = "def fix(): return False\n"

    # Record a failed attempt
    mgr.record_modification_attempt(
        file_path=file_path,
        patch_or_new_content=failed_patch,
        content_before="def fix(): pass",
        content_after=failed_patch,
        success=False,
        error="AssertionError",
    )

    # Attempting the exact same patch again should raise SafeguardViolationError
    with pytest.raises(SafeguardViolationError) as exc_info:
        mgr.check_repeated_fix_safeguard(file_path, failed_patch)
    assert "identical to a previously failed attempt" in str(exc_info.value)


@pytest.mark.asyncio
async def test_structured_failure_explanation():
    """Verify generation of structured failure report when task fails repeatedly."""
    provider = MockAIProvider()
    sandbox = InMemorySandbox(test_should_pass=False)
    coder = CodingAgent(provider=provider, sandbox=sandbox, sandbox_id="sb_1")

    # Record a modification attempt
    await coder.modify_file_safely(
        file_path="app/failing.py",
        proposed_content_or_patch="def fail(): raise ValueError()",
        reason="Attempt fix",
        related_requirement="REQ-999",
    )

    report: StructuredFailureReport = coder.generate_failure_report(
        task_id="task_123",
        run_id="run_456",
        failure_reason="Max test attempts (5) reached",
        failing_stage="TESTING",
        error_or_trace="AssertionError: assert 1 == 2",
        root_cause_analysis="The login service returns HTTP 401 due to unhashed password comparison.",
        recommendations=["Update hash computation in auth_service.py."],
    )

    assert report.task_id == "task_123"
    assert report.run_id == "run_456"
    assert report.failure_reason == "Max test attempts (5) reached"
    assert "app/failing.py" in report.modified_files
    assert report.attempted_fixes_count == 1

    markdown_output = report.to_markdown()
    assert "# Coding Task Failure Report" in markdown_output
    assert "Max test attempts (5) reached" in markdown_output
    assert "AssertionError: assert 1 == 2" in markdown_output
    assert "Update hash computation in auth_service.py." in markdown_output
