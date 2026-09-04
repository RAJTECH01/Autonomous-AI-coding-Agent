import uuid
import pytest
from datetime import datetime, timezone
from typing import Dict, Any

from app.domain.entities.agent import AgentRun, AgentLimits, AgentState
from app.domain.entities.tool import ToolPermission, ToolExecutionStatus, mask_sensitive_data
from app.domain.interfaces.sandbox import SandboxInterface, CommandResult
from app.infrastructure.tools.base import BaseTool, ToolResult
from app.infrastructure.tools.registry import ToolRegistry
from app.infrastructure.tools.path_validator import PathValidator, PathSecurityError
from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer
from app.core.exceptions import ToolExecutionError, LimitExceededError


class DummySandbox(SandboxInterface):
    """Mock sandbox for testing tool execution pipeline."""

    def __init__(self):
        self.files: Dict[str, str] = {
            "main.py": "print('hello world')",
            "utils.py": "def add(a, b):\n    return a + b",
        }
        self.executed_commands = []

    async def create_sandbox(self, project_id: str, timeout_seconds: int = 3600) -> str:
        return "sb_test_123"

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120) -> CommandResult:
        self.executed_commands.append(command)
        if "pytest" in command:
            return CommandResult(command=command, exit_code=0, stdout="================ 2 passed in 0.05s ================", stderr="", duration_ms=50)
        elif "git status" in command:
            return CommandResult(command=command, exit_code=0, stdout="## main\n M main.py\n?? new_file.py", stderr="", duration_ms=30)
        elif "git diff" in command:
            return CommandResult(command=command, exit_code=0, stdout="main.py | 2 +-\n 1 file changed", stderr="", duration_ms=20)
        elif "ls" in command or "find" in command:
            return CommandResult(command=command, exit_code=0, stdout="main.py\nutils.py", stderr="", duration_ms=20)
        elif "tree" in command:
            return CommandResult(command=command, exit_code=0, stdout=".\n├── main.py\n└── utils.py", stderr="", duration_ms=20)
        elif "grep" in command:
            return CommandResult(command=command, exit_code=0, stdout="./main.py:1:print('hello world')", stderr="", duration_ms=20)
        elif "rm " in command:
            return CommandResult(command=command, exit_code=0, stdout="deleted", stderr="", duration_ms=20)
        elif "test -f" in command:
            return CommandResult(command=command, exit_code=1, stdout="", stderr="", duration_ms=10)
        else:
            return CommandResult(command=command, exit_code=0, stdout="Command executed successfully", stderr="", duration_ms=40)

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        if file_path not in self.files:
            raise FileNotFoundError(f"File not found: {file_path}")
        return self.files[file_path]

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        self.files[file_path] = content
        return True

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        return True


def create_sample_run() -> AgentRun:
    return AgentRun(
        id=str(uuid.uuid4()),
        task_id=str(uuid.uuid4()),
        state=AgentState.IMPLEMENTING,
        limits=AgentLimits(max_tool_calls=20, max_files_changed=5, max_generated_output=1000),
    )


# 1. Registry & Unknown Tool Rejection
def test_tool_registry_initialization_and_unknown_tool():
    registry = ToolRegistry()
    assert len(registry.get_all_tools()) >= 10

    # Verify all 10 initial tool names exist
    expected_tools = [
        "list_files", "read_file", "write_file", "create_file", "delete_file",
        "search_files", "execute_command", "run_tests", "get_project_structure", "get_git_status"
    ]
    for t_name in expected_tools:
        assert registry.has_tool(t_name)

    # Unknown tool rejection
    with pytest.raises(ToolExecutionError) as exc_info:
        registry.get_tool("unregistered_malicious_tool")
    assert "Unknown tool 'unregistered_malicious_tool'" in str(exc_info.value)


# 2. Path Security Engine Tests
def test_path_validator_security_rules():
    # Path traversal rejection
    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path("../../etc/passwd")

    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path("src/../../secret.txt")

    # System directory rejection
    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path("/etc/shadow")

    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path("C:\\Windows\\System32\\cmd.exe")

    # Secret & credential files rejection
    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path(".env")

    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path(".env.production")

    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path("id_rsa")

    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path("server.pem")

    with pytest.raises(PathSecurityError):
        PathValidator.validate_workspace_path("credentials.json")

    # Clean path resolution inside workspace
    valid_path = PathValidator.validate_workspace_path("src/app/main.py")
    assert valid_path == "src/app/main.py" or valid_path == "src/app/main.py".replace("/", "\\")


# 3. Input Schema Validation
@pytest.mark.asyncio
async def test_input_schema_validation():
    tool_layer = ControlledToolLayer()
    sandbox = DummySandbox()
    run = create_sample_run()

    # Invalid read_file missing required argument
    with pytest.raises(ToolExecutionError) as exc:
        await tool_layer.execute_tool(
            sandbox, "sb_123", "read_file", {}, run
        )
    assert "validation failed" in str(exc.value).lower()


# 4. Secret Masking in Audit Logs
def test_secret_masking_helper():
    raw_input = {
        "file_path": "config.json",
        "api_key": "sk-1234567890secretkey",
        "user_password": "SuperSecretPassword123!",
        "auth_token": "bearer eyJhbGciOi...",
        "nested": {
            "jwt_secret": "my-nested-secret",
            "normal_field": "public_value",
        },
    }
    masked = mask_sensitive_data(raw_input)
    assert masked["api_key"] == "********"
    assert masked["user_password"] == "********"
    assert masked["auth_token"] == "********"
    assert masked["nested"]["jwt_secret"] == "********"
    assert masked["nested"]["normal_field"] == "public_value"
    assert masked["file_path"] == "config.json"


# 5. Permission Validation
@pytest.mark.asyncio
async def test_permission_authorization_check():
    tool_layer = ControlledToolLayer()
    sandbox = DummySandbox()
    run = create_sample_run()

    # User role trying to execute command requiring EXECUTE permission
    res = await tool_layer.execute_tool(
        sandbox, "sb_123", "execute_command", {"command": "echo hello"}, run, user_role="user"
    )
    assert res.success is False
    assert "Permission denied" in res.error

    # Administrator role allowed
    res_admin = await tool_layer.execute_tool(
        sandbox, "sb_123", "execute_command", {"command": "echo hello"}, run, user_role="administrator"
    )
    assert res_admin.success is True


# 6. File Tools Execution
@pytest.mark.asyncio
async def test_file_tools_execution():
    tool_layer = ControlledToolLayer()
    sandbox = DummySandbox()
    run = create_sample_run()

    # read_file
    read_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "read_file", {"file_path": "main.py"}, run
    )
    assert read_res.success is True
    assert "print('hello world')" in read_res.output

    # write_file
    write_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "write_file", {"file_path": "app.py", "content": "import sys"}, run
    )
    assert write_res.success is True
    assert "app.py" in sandbox.files

    # create_file
    create_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "create_file", {"file_path": "new_module.py", "initial_content": "# new"}, run
    )
    assert create_res.success is True
    assert "new_module.py" in sandbox.files

    # delete_file
    del_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "delete_file", {"file_path": "utils.py"}, run
    )
    assert del_res.success is True

    # search_files
    search_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "search_files", {"query": "hello"}, run
    )
    assert search_res.success is True

    # list_files
    list_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "list_files", {"directory_path": "."}, run
    )
    assert list_res.success is True

    # get_project_structure
    tree_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "get_project_structure", {"max_depth": 2}, run
    )
    assert tree_res.success is True


# 7. Execution & Git Tools
@pytest.mark.asyncio
async def test_execution_and_git_tools():
    tool_layer = ControlledToolLayer()
    sandbox = DummySandbox()
    run = create_sample_run()

    # execute_command
    cmd_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "execute_command", {"command": "echo test"}, run
    )
    assert cmd_res.success is True

    # run_tests
    test_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "run_tests", {"test_path": "tests/"}, run
    )
    assert test_res.success is True
    assert "2 passed" in test_res.output

    # get_git_status
    git_res = await tool_layer.execute_tool(
        sandbox, "sb_123", "get_git_status", {"include_diff": True}, run
    )
    assert git_res.success is True
    assert "main" in git_res.output


# 8. Security Blocking & Audit Log Recording
@pytest.mark.asyncio
async def test_audit_logging_and_path_security_rejection():
    tool_layer = ControlledToolLayer()
    sandbox = DummySandbox()
    run = create_sample_run()

    # Attempt secret file access (.env)
    res = await tool_layer.execute_tool(
        sandbox, "sb_123", "read_file", {"file_path": ".env"}, run
    )
    assert res.success is False
    assert "strictly forbidden" in res.error

    # Verify audit record was created and status marked DENIED
    assert len(tool_layer.audit_records) == 1
    record = tool_layer.audit_records[0]
    assert record.tool_name == "read_file"
    assert record.status == ToolExecutionStatus.DENIED
    assert record.input_metadata["file_path"] == ".env"
