"""Sandbox tests: containment, limits, lifecycle and real code execution.

Two layers here:

* Portable layer - runs everywhere. Uses ``InProcessSandbox``, which applies the
  **production** containment policy and executes real Python subprocesses, so
  "generated syntax error" and "runtime error" are genuine interpreter output.
* Docker layer - marked ``docker`` and skipped when no daemon is reachable. This
  is where container isolation itself (network off, read-only rootfs, memory and
  pid caps) is verified against the real runtime.
"""

import os
import shutil

import pytest

from app.core.config import settings
from app.core.exceptions import SandboxExecutionError
from app.infrastructure.sandbox.docker_sandbox import DockerSandboxAdapter
from app.infrastructure.sandbox.policy import SandboxSecurityPolicy

from tests.support.factories import (
    RUNTIME_ERROR_PROJECT,
    SYNTAX_ERROR_PROJECT,
    write_workspace,
)
from tests.support.sandboxes import InProcessSandbox

pytestmark = pytest.mark.sandbox


def docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


requires_docker = pytest.mark.skipif(not docker_available(), reason="no reachable Docker daemon")


# ------------------------------------------------------------- containment
@pytest.mark.integration
class TestWorkspaceContainment:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        ["../escape.txt", "../../etc/passwd", "sub/../../../../escape.txt"],
    )
    async def test_traversal_reads_are_refused(self, sandbox, path):
        sb, sandbox_id = sandbox
        with pytest.raises(SandboxExecutionError, match="escapes workspace boundary"):
            await sb.read_file(sandbox_id, path)

    @pytest.mark.asyncio
    async def test_traversal_writes_are_refused(self, sandbox):
        sb, sandbox_id = sandbox
        with pytest.raises(SandboxExecutionError, match="escapes workspace boundary"):
            await sb.write_file(sandbox_id, "../../pwned.txt", "payload")

    @pytest.mark.asyncio
    async def test_writes_land_inside_the_workspace_only(self, sandbox):
        sb, sandbox_id = sandbox
        await sb.write_file(sandbox_id, "nested/dir/file.txt", "content")
        expected = os.path.join(sb.workdir(sandbox_id), "nested", "dir", "file.txt")
        assert os.path.isfile(expected)

    @pytest.mark.asyncio
    async def test_unknown_sandbox_id_is_rejected(self):
        sb = InProcessSandbox()
        with pytest.raises(SandboxExecutionError, match="not found"):
            await sb.execute_command("sb-does-not-exist", "echo hi")

    @pytest.mark.asyncio
    async def test_missing_file_read_is_an_error_not_an_empty_string(self, sandbox):
        sb, sandbox_id = sandbox
        with pytest.raises(SandboxExecutionError, match="File not found"):
            await sb.read_file(sandbox_id, "absent.txt")


# ------------------------------------------------------- real code execution
@pytest.mark.integration
class TestRealCodeExecution:
    @pytest.mark.asyncio
    async def test_valid_code_runs_and_reports_success(self, sandbox):
        sb, sandbox_id = sandbox
        await sb.write_file(sandbox_id, "ok.py", "print('hello from sandbox')\n")
        result = await sb.execute_command(sandbox_id, "python ok.py")
        assert result.exit_code == 0
        assert "hello from sandbox" in result.stdout

    @pytest.mark.asyncio
    async def test_generated_syntax_error_is_reported_with_diagnostics(self, sandbox):
        sb, sandbox_id = sandbox
        write_workspace(sb.workdir(sandbox_id), SYNTAX_ERROR_PROJECT)
        result = await sb.execute_command(sandbox_id, "python broken.py")
        assert result.exit_code != 0
        assert "SyntaxError" in result.stderr

    @pytest.mark.asyncio
    async def test_generated_runtime_error_is_reported_with_traceback(self, sandbox):
        sb, sandbox_id = sandbox
        write_workspace(sb.workdir(sandbox_id), RUNTIME_ERROR_PROJECT)
        await sb.write_file(sandbox_id, "boom.py", "from runtime import load_config\nload_config({})\n")
        result = await sb.execute_command(sandbox_id, "python boom.py")
        assert result.exit_code != 0
        assert "KeyError" in result.stderr
        assert "Traceback" in result.stderr

    @pytest.mark.asyncio
    async def test_nonexistent_program_yields_127(self, sandbox):
        sb, sandbox_id = sandbox
        result = await sb.execute_command(sandbox_id, "definitely_not_a_program --help")
        assert result.exit_code == 127

    @pytest.mark.asyncio
    async def test_large_output_is_truncated(self, sandbox, monkeypatch):
        sb, sandbox_id = sandbox
        monkeypatch.setattr(settings, "SANDBOX_MAX_OUTPUT_BYTES", 2048)
        await sb.write_file(sandbox_id, "flood.py", "print('X' * 200000)\n")
        result = await sb.execute_command(sandbox_id, "python flood.py")
        assert result.truncated is True
        assert "TRUNCATED" in result.stdout


# ----------------------------------------------------------------- lifecycle
@pytest.mark.integration
class TestSandboxLifecycle:
    @pytest.mark.asyncio
    async def test_workspace_is_seeded_from_a_project_directory(self, project_sandbox):
        sb, sandbox_id = await project_sandbox(SYNTAX_ERROR_PROJECT)
        assert "def add(a, b)" in await sb.read_file(sandbox_id, "broken.py")

    @pytest.mark.asyncio
    async def test_destroy_removes_the_workspace_from_disk(self):
        sb = InProcessSandbox()
        sandbox_id = await sb.create_sandbox("lifecycle")
        workdir = sb.workdir(sandbox_id)
        await sb.write_file(sandbox_id, "secret_work.txt", "customer source code")
        assert os.path.isdir(workdir)

        assert await sb.destroy_sandbox(sandbox_id) is True
        assert not os.path.exists(workdir), "workspace data outlived the sandbox"

    @pytest.mark.asyncio
    async def test_destroying_twice_is_harmless(self):
        sb = InProcessSandbox()
        sandbox_id = await sb.create_sandbox("lifecycle")
        assert await sb.destroy_sandbox(sandbox_id) is True
        assert await sb.destroy_sandbox(sandbox_id) is False

    @pytest.mark.asyncio
    async def test_sandboxes_are_isolated_from_each_other(self):
        sb = InProcessSandbox()
        first = await sb.create_sandbox("tenant-a")
        second = await sb.create_sandbox("tenant-b")
        try:
            await sb.write_file(first, "notes.txt", "tenant A private data")
            with pytest.raises(SandboxExecutionError):
                await sb.read_file(second, "notes.txt")
        finally:
            await sb.destroy_sandbox(first)
            await sb.destroy_sandbox(second)


# ------------------------------------------------- adapter failure behaviour
class TestDockerAdapterFailureModes:
    @pytest.mark.asyncio
    async def test_creation_fails_closed_when_the_daemon_is_unavailable(self, monkeypatch):
        adapter = DockerSandboxAdapter()
        monkeypatch.setattr(adapter, "docker_client", None)
        monkeypatch.setattr(settings, "SANDBOX_ALLOW_HOST_FALLBACK", False)

        with pytest.raises(SandboxExecutionError, match="host execution fallback is disabled"):
            await adapter.create_sandbox("session-x")

    @pytest.mark.asyncio
    async def test_failed_creation_leaves_no_workspace_behind(self, monkeypatch, tmp_path):
        adapter = DockerSandboxAdapter()
        monkeypatch.setattr(adapter, "docker_client", None)
        monkeypatch.setattr(settings, "SANDBOX_ALLOW_HOST_FALLBACK", False)
        monkeypatch.setattr("app.infrastructure.sandbox.docker_sandbox.tempfile.gettempdir", lambda: str(tmp_path))

        with pytest.raises(SandboxExecutionError):
            await adapter.create_sandbox("session-y")

        leftovers = list((tmp_path / "agent_sandboxes").glob("*")) if (tmp_path / "agent_sandboxes").exists() else []
        assert leftovers == [], f"orphaned workspace directories: {leftovers}"

    @pytest.mark.asyncio
    async def test_executing_in_an_unknown_sandbox_is_rejected(self):
        adapter = DockerSandboxAdapter()
        with pytest.raises(SandboxExecutionError, match="not found"):
            await adapter.execute_command("sb_missing", "echo hi")

    @pytest.mark.asyncio
    async def test_destroying_an_unknown_sandbox_returns_false(self):
        assert await DockerSandboxAdapter().destroy_sandbox("sb_missing") is False


# --------------------------------------------------- real container isolation
@requires_docker
@pytest.mark.docker
@pytest.mark.slow
@pytest.mark.integration
class TestRealContainerIsolation:
    @pytest.mark.asyncio
    async def test_command_runs_inside_a_real_container(self):
        adapter = DockerSandboxAdapter()
        sandbox_id = await adapter.create_sandbox("docker-session")
        try:
            result = await adapter.execute_command(sandbox_id, "echo container-alive")
            assert result.exit_code == 0
            assert "container-alive" in result.stdout
        finally:
            await adapter.destroy_sandbox(sandbox_id)

    @pytest.mark.asyncio
    async def test_network_egress_is_blocked(self):
        adapter = DockerSandboxAdapter()
        sandbox_id = await adapter.create_sandbox("docker-session")
        try:
            result = await adapter.execute_command(
                sandbox_id,
                "python -c \"import socket; socket.create_connection(('1.1.1.1', 443), timeout=5)\"",
            )
            assert result.exit_code != 0, "sandbox reached the network"
        finally:
            await adapter.destroy_sandbox(sandbox_id)

    @pytest.mark.asyncio
    async def test_root_filesystem_is_read_only(self):
        adapter = DockerSandboxAdapter()
        sandbox_id = await adapter.create_sandbox("docker-session")
        try:
            result = await adapter.execute_command(sandbox_id, "touch /etc/should_not_write")
            assert result.exit_code != 0
        finally:
            await adapter.destroy_sandbox(sandbox_id)

    @pytest.mark.asyncio
    async def test_workspace_is_writable(self):
        adapter = DockerSandboxAdapter()
        sandbox_id = await adapter.create_sandbox("docker-session")
        try:
            await adapter.write_file(sandbox_id, "artifact.txt", "generated")
            assert await adapter.read_file(sandbox_id, "artifact.txt") == "generated"
        finally:
            await adapter.destroy_sandbox(sandbox_id)

    @pytest.mark.asyncio
    async def test_timeout_terminates_the_process(self):
        adapter = DockerSandboxAdapter()
        sandbox_id = await adapter.create_sandbox("docker-session")
        try:
            with pytest.raises(SandboxExecutionError, match="timed out"):
                await adapter.execute_command(sandbox_id, "sleep 30", timeout_seconds=2)
        finally:
            await adapter.destroy_sandbox(sandbox_id)

    @pytest.mark.asyncio
    async def test_container_and_workspace_are_removed_on_destroy(self):
        adapter = DockerSandboxAdapter()
        sandbox_id = await adapter.create_sandbox("docker-session")
        workdir = adapter._sandboxes[sandbox_id]["workdir"]
        container_id = adapter._sandboxes[sandbox_id]["container_id"]

        assert await adapter.destroy_sandbox(sandbox_id) is True
        assert not os.path.exists(workdir)

        import docker
        from docker.errors import NotFound

        with pytest.raises(NotFound):
            docker.from_env().containers.get(container_id)


# ---------------------------------------------------------- policy plumbing
class TestPolicyIsActuallyApplied:
    def test_adapter_requests_the_hardened_option_set(self):
        opts = SandboxSecurityPolicy.get_container_security_options(
            max_cpus=settings.SANDBOX_MAX_CPUS,
            max_memory_mb=settings.SANDBOX_MAX_MEMORY_MB,
            max_pids=settings.SANDBOX_MAX_PIDS,
            log_max_size=settings.SANDBOX_LOG_MAX_SIZE,
            network_enabled=False,
        )
        assert opts["network_mode"] == "none"
        assert opts["mem_limit"] == f"{settings.SANDBOX_MAX_MEMORY_MB}m"
        assert opts["memswap_limit"] == opts["mem_limit"], "swap must not extend the memory cap"
        assert opts["pids_limit"] == settings.SANDBOX_MAX_PIDS
        assert opts["log_config"]["config"]["max-size"] == settings.SANDBOX_LOG_MAX_SIZE
