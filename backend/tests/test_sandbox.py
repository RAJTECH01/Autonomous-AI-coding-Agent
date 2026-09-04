import os
import sys
import pytest

from unittest.mock import MagicMock, patch

from app.domain.interfaces.sandbox import CommandResult
from app.core.config import settings
from app.core.exceptions import SandboxExecutionError
from app.infrastructure.sandbox.policy import SandboxSecurityPolicy, SecurityPolicyError
from app.infrastructure.sandbox.runtimes import runtime_registry
from app.infrastructure.sandbox.audit import audit_logger, SandboxAuditEventType
from app.infrastructure.sandbox.docker_sandbox import DockerSandboxAdapter


# 1. Environment Variable Sanitization & Allowlist (Requirements 14 & 15)
def test_environment_variable_sanitization_and_allowlist():
    raw_env = {
        "PATH": "/custom/bin",
        "AWS_SECRET_ACCESS_KEY": "AKIA12345SECRETKEY",
        "POSTGRES_PASSWORD": "supersecretpassword",
        "API_TOKEN": "bearer-token-12345",
        "CUSTOM_APP_SETTING": "my_safe_value",
    }
    sanitized = SandboxSecurityPolicy.sanitize_environment(raw_env)

    assert "AWS_SECRET_ACCESS_KEY" not in sanitized
    assert "POSTGRES_PASSWORD" not in sanitized
    assert "API_TOKEN" not in sanitized
    assert sanitized["CUSTOM_APP_SETTING"] == "my_safe_value"
    assert sanitized["PYTHONUNBUFFERED"] == "1"
    assert "TMPDIR" in sanitized



# 2. Output Size Limits & Truncation (Requirement 16)
def test_output_size_limit_truncation():
    large_output = "A" * 2000
    truncated_str, was_truncated = SandboxSecurityPolicy.truncate_output(large_output, max_bytes=1000)

    assert was_truncated is True
    assert "[TRUNCATED: Maximum execution output limit of 1000 bytes exceeded]" in truncated_str
    assert len(truncated_str) < 2000

    small_output = "Hello World"
    normal_str, was_truncated_normal = SandboxSecurityPolicy.truncate_output(small_output, max_bytes=1000)
    assert was_truncated_normal is False
    assert normal_str == "Hello World"


# 3. Path Boundary & Directory Traversal Prevention (Requirements 6 & 11)
def test_workspace_boundary_path_validation():
    workdir = "/tmp/agent_sandboxes/sb_test_123"

    # Valid relative path inside workspace
    valid_path = SandboxSecurityPolicy.validate_workspace_relative_path(workdir, "src/app.py")
    assert valid_path.startswith(os.path.abspath(workdir))

    # Malicious path escape attempt
    with pytest.raises(SecurityPolicyError) as exc_info:
        SandboxSecurityPolicy.validate_workspace_relative_path(workdir, "../../etc/passwd")
    assert "escapes workspace boundary" in str(exc_info.value)


# 4. Multi-Language Runtime Registry
def test_multi_language_runtime_registry():
    python_rt = runtime_registry.get_runtime("python")
    assert python_rt.image == "python:3.11-slim"
    assert python_rt.default_command == "python"

    node_rt = runtime_registry.get_runtime(".ts")
    assert node_rt.name == "node"
    assert node_rt.image == "node:20-alpine"

    go_rt = runtime_registry.get_runtime("go")
    assert go_rt.image == "golang:1.22-alpine"

    rust_rt = runtime_registry.get_runtime("rust")
    assert rust_rt.image == "rust:1.75-slim"


# 5. Security Container Options (Requirements 2, 3, 4, 6, 7, 8, 12, 13, 17)
def test_container_security_options():
    sec_opts = SandboxSecurityPolicy.get_container_security_options(
        max_cpus=2.0,
        max_memory_mb=512,
        max_pids=100,
        log_max_size="5m",
        network_enabled=False,
    )

    assert sec_opts["read_only"] is True  # Read-only root
    assert sec_opts["cap_drop"] == ["ALL"]  # Drop all capabilities
    assert sec_opts["security_opt"] == ["no-new-privileges:true"]  # No privilege escalation
    assert sec_opts["privileged"] is False  # Non-privileged
    assert sec_opts["network_mode"] == "none"  # Disabled network access
    assert sec_opts["nano_cpus"] == int(2.0 * 1e9)
    assert sec_opts["mem_limit"] == "512m"
    assert sec_opts["pids_limit"] == 100
    assert "/tmp" in sec_opts["tmpfs"]
    assert sec_opts["log_config"]["config"]["max-size"] == "5m"


# 6. Untrusted Host Execution Blocked (Requirement 11)
@pytest.mark.asyncio
async def test_host_execution_blocked_when_fallback_disabled():
    adapter = DockerSandboxAdapter()
    adapter.docker_client = None  # Simulate no Docker daemon available

    with patch.object(settings, "SANDBOX_ALLOW_HOST_FALLBACK", False):
        with pytest.raises(SandboxExecutionError) as exc_info:
            await adapter.create_sandbox("test_session_fallback", workspace_path="", runtime="python")
        assert "Untrusted host execution fallback is disabled" in str(exc_info.value)


# 7. Sandbox Operations & Audit Trail (Requirements 1, 9, 10, 19, 20)
@pytest.mark.asyncio
async def test_sandbox_file_ops_and_audit_trail():
    adapter = DockerSandboxAdapter()

    # Enable fallback for local mock testing without requiring running Docker daemon
    with patch.object(settings, "SANDBOX_ALLOW_HOST_FALLBACK", True):
        sandbox_id = await adapter.create_sandbox("audit_test_session", workspace_path="")
        try:
            # Write file
            written = await adapter.write_file(sandbox_id, "script.py", "print('hello audit')")
            assert written is True

            # Read file
            content = await adapter.read_file(sandbox_id, "script.py")
            assert content == "print('hello audit')"

            # Execute command
            cmd_res = await adapter.execute_command(sandbox_id, f"{sys.executable} script.py")
            assert cmd_res.exit_code == 0
            assert "hello audit" in cmd_res.stdout


            # Path traversal rejection check
            with pytest.raises(SandboxExecutionError):
                await adapter.read_file(sandbox_id, "../../../secret.txt")

            # Check audit records logged
            records = audit_logger.get_records_for_sandbox(sandbox_id)
            event_types = [r.event_type for r in records]

            assert SandboxAuditEventType.SANDBOX_CREATED in event_types
            assert SandboxAuditEventType.FILE_WRITTEN in event_types
            assert SandboxAuditEventType.FILE_READ in event_types
            assert SandboxAuditEventType.COMMAND_EXECUTED in event_types
            assert SandboxAuditEventType.SECURITY_VIOLATION in event_types

        finally:
            await adapter.destroy_sandbox(sandbox_id)
            records_after = audit_logger.get_records_for_sandbox(sandbox_id)
            event_types_after = [r.event_type for r in records_after]
            assert SandboxAuditEventType.SANDBOX_DESTROYED in event_types_after


# 8. Async Context Manager Auto Cleanup (Requirement 10)
@pytest.mark.asyncio
async def test_sandbox_async_context_manager():
    with patch.object(settings, "SANDBOX_ALLOW_HOST_FALLBACK", True):
        async with DockerSandboxAdapter() as adapter:
            sb_id = await adapter.create_sandbox("ctx_session", workspace_path="")
            await adapter.write_file(sb_id, "test.txt", "data")
            assert len(adapter._sandboxes) == 1

        # After exiting context manager, all sandboxes destroyed automatically
        assert len(adapter._sandboxes) == 0
