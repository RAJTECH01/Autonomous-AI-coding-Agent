import os
import uuid
import time
import asyncio
import tempfile
import shutil
from typing import Dict, Any, Optional, List
import docker
from docker.models.containers import Container

from app.domain.interfaces.sandbox import SandboxInterface, CommandResult
from app.core.config import settings
from app.core.logging import logger
from app.core.exceptions import SandboxExecutionError
from app.infrastructure.sandbox.policy import SandboxSecurityPolicy, SecurityPolicyError
from app.infrastructure.sandbox.runtimes import runtime_registry, LanguageRuntime
from app.infrastructure.sandbox.audit import (
    audit_logger,
    SandboxAuditRecord,
    SandboxAuditEventType,
)


class DockerSandboxAdapter(SandboxInterface):
    """
    Production-grade secure Docker sandbox implementation.
    Enforces process, memory, CPU, filesystem, network, output, and privilege isolation
    for running untrusted AI-generated code.
    """

    def __init__(self):
        self._sandboxes: Dict[str, Dict[str, Any]] = {}
        try:
            self.docker_client = docker.from_env()
            # Verify daemon connectivity
            self.docker_client.ping()
        except Exception as e:
            logger.warning("Docker SDK client init failed or daemon unreachable", error=str(e))
            self.docker_client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.destroy_all_sandboxes()

    async def create_sandbox(
        self,
        session_id: str,
        workspace_path: str = "",
        runtime: str = "python",
        env_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Creates an isolated container environment per task run.
        Requirements 1, 2, 3, 4, 6, 7, 8, 9, 12, 13, 14, 15, 17, 20
        """
        unique_run_id = uuid.uuid4().hex[:8]
        sandbox_id = f"sb_{session_id}_{unique_run_id}"

        # 1. Ephemeral Temporary Workspace Creation (Requirement 9)
        temp_dir = os.path.join(tempfile.gettempdir(), "agent_sandboxes", sandbox_id)
        os.makedirs(temp_dir, exist_ok=True)

        if workspace_path and os.path.exists(workspace_path) and os.path.isdir(workspace_path):
            shutil.copytree(workspace_path, temp_dir, dirs_exist_ok=True)

        # 2. Select Language Runtime (Multi-Language Architecture)
        lang_runtime = runtime_registry.get_runtime(runtime)

        # 3. Environment Variable Sanitization & Allowlist (Requirements 14 & 15)
        sanitized_env = SandboxSecurityPolicy.sanitize_environment(env_vars)

        container_id = None
        if self.docker_client:
            try:
                # 4. Security Configuration & Container Run kwargs (Requirements 2, 3, 4, 6, 7, 8, 12, 13, 17)
                sec_opts = SandboxSecurityPolicy.get_container_security_options(
                    max_cpus=settings.SANDBOX_MAX_CPUS,
                    max_memory_mb=settings.SANDBOX_MAX_MEMORY_MB,
                    max_pids=settings.SANDBOX_MAX_PIDS,
                    log_max_size=settings.SANDBOX_LOG_MAX_SIZE,
                    network_enabled=False,  # Requirement 7: Network disabled by default
                )

                container = self.docker_client.containers.run(
                    image=lang_runtime.image,
                    command="tail -f /dev/null",  # Keep container idle awaiting commands
                    detach=True,
                    name=sandbox_id,
                    volumes={temp_dir: {"bind": "/workspace", "mode": "rw"}},
                    working_dir="/workspace",
                    environment=sanitized_env,
                    **sec_opts
                )
                container_id = container.id
                logger.info(
                    "Secure Docker sandbox container created",
                    sandbox_id=sandbox_id,
                    container_id=container_id[:12],
                    image=lang_runtime.image,
                )
            except Exception as e:
                logger.error("Failed to launch Docker sandbox container", sandbox_id=sandbox_id, error=str(e))
                # Cleanup tempdir if container fails to start
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise SandboxExecutionError(f"Container initialization failed: {str(e)}")

        elif not settings.SANDBOX_ALLOW_HOST_FALLBACK:
            # Requirement 11: Direct OS execution on host is strictly disallowed for untrusted code
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise SandboxExecutionError(
                "Untrusted host execution fallback is disabled. Docker container engine is required."
            )

        self._sandboxes[sandbox_id] = {
            "container_id": container_id,
            "workdir": temp_dir,
            "session_id": session_id,
            "runtime": lang_runtime.name,
            "created_at": time.time(),
        }

        # Requirement 20: Audit Event Logging
        audit_logger.record_event(
            SandboxAuditRecord(
                event_id=uuid.uuid4().hex,
                event_type=SandboxAuditEventType.SANDBOX_CREATED,
                sandbox_id=sandbox_id,
                session_id=session_id,
                details={
                    "runtime": lang_runtime.name,
                    "image": lang_runtime.image,
                    "container_id": container_id[:12] if container_id else None,
                    "max_cpus": settings.SANDBOX_MAX_CPUS,
                    "max_memory_mb": settings.SANDBOX_MAX_MEMORY_MB,
                    "max_pids": settings.SANDBOX_MAX_PIDS,
                    "network_disabled": True,
                },
            )
        )
        return sandbox_id

    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        timeout_seconds: int = 120,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """
        Executes a command safely inside the isolated container with process termination
        on timeout and output size limits.
        Requirements 5, 11, 16, 18, 20
        """
        if sandbox_id not in self._sandboxes:
            raise SandboxExecutionError(f"Sandbox '{sandbox_id}' not found")

        sandbox_info = self._sandboxes[sandbox_id]
        container_id = sandbox_info.get("container_id")
        session_id = sandbox_info["session_id"]
        workdir = sandbox_info["workdir"]

        exec_env = SandboxSecurityPolicy.sanitize_environment(env_vars)
        start_time = time.time()

        if container_id and self.docker_client:
            try:
                container: Container = self.docker_client.containers.get(container_id)

                # Execute inside container asynchronously to enforce timeout & termination
                async def _run_container_exec():
                    return await asyncio.to_thread(
                        container.exec_run,
                        cmd=["sh", "-c", command],
                        workdir="/workspace",
                        environment=exec_env,
                        demux=True,
                    )

                try:
                    exec_res = await asyncio.wait_for(_run_container_exec(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    # Requirement 18: Process termination on timeout
                    # Restart/kill exec process by restarting container cleanly
                    logger.warning("Sandbox command timed out, restarting container", sandbox_id=sandbox_id)
                    try:
                        container.restart(timeout=1)
                    except Exception as restart_err:
                        logger.error("Error restarting container on timeout", error=str(restart_err))

                    audit_logger.record_event(
                        SandboxAuditRecord(
                            event_id=uuid.uuid4().hex,
                            event_type=SandboxAuditEventType.TIMEOUT_EXCEEDED,
                            sandbox_id=sandbox_id,
                            session_id=session_id,
                            command=command,
                            details={"timeout_seconds": timeout_seconds},
                        )
                    )
                    raise SandboxExecutionError(
                        f"Execution timed out after {timeout_seconds} seconds. Process terminated."
                    )

                duration_ms = int((time.time() - start_time) * 1000)

                raw_stdout = exec_res.output[0].decode("utf-8", errors="replace") if exec_res.output[0] else ""
                raw_stderr = exec_res.output[1].decode("utf-8", errors="replace") if exec_res.output[1] else ""

                # Requirement 16: Output Size Limits & Truncation
                stdout, trunc_out = SandboxSecurityPolicy.truncate_output(
                    raw_stdout, max_bytes=settings.SANDBOX_MAX_OUTPUT_BYTES
                )
                stderr, trunc_err = SandboxSecurityPolicy.truncate_output(
                    raw_stderr, max_bytes=settings.SANDBOX_MAX_OUTPUT_BYTES
                )
                was_truncated = trunc_out or trunc_err

                result = CommandResult(
                    command=command,
                    exit_code=exec_res.exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration_ms,
                    truncated=was_truncated,
                    runtime=sandbox_info.get("runtime", "python"),
                )

                # Requirement 20: Audit Event Recording
                audit_logger.record_event(
                    SandboxAuditRecord(
                        event_id=uuid.uuid4().hex,
                        event_type=SandboxAuditEventType.COMMAND_EXECUTED,
                        sandbox_id=sandbox_id,
                        session_id=session_id,
                        command=command,
                        exit_code=exec_res.exit_code,
                        duration_ms=duration_ms,
                        output_truncated=was_truncated,
                    )
                )
                return result

            except SandboxExecutionError:
                raise
            except Exception as e:
                logger.error("Container execution error", sandbox_id=sandbox_id, error=str(e))
                raise SandboxExecutionError(f"Container command execution failed: {str(e)}")

        elif settings.SANDBOX_ALLOW_HOST_FALLBACK:
            # Fallback ONLY if explicitly configured for local debug/testing
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=workdir,
                    env=exec_env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_seconds
                )
                duration_ms = int((time.time() - start_time) * 1000)

                stdout, trunc_out = SandboxSecurityPolicy.truncate_output(
                    stdout_bytes.decode("utf-8", errors="replace"), settings.SANDBOX_MAX_OUTPUT_BYTES
                )
                stderr, trunc_err = SandboxSecurityPolicy.truncate_output(
                    stderr_bytes.decode("utf-8", errors="replace"), settings.SANDBOX_MAX_OUTPUT_BYTES
                )

                audit_logger.record_event(
                    SandboxAuditRecord(
                        event_id=uuid.uuid4().hex,
                        event_type=SandboxAuditEventType.COMMAND_EXECUTED,
                        sandbox_id=sandbox_id,
                        session_id=session_id,
                        command=command,
                        exit_code=proc.returncode or 0,
                        duration_ms=duration_ms,
                        output_truncated=trunc_out or trunc_err,
                    )
                )

                return CommandResult(
                    command=command,
                    exit_code=proc.returncode or 0,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration_ms,
                    truncated=trunc_out or trunc_err,
                    runtime=sandbox_info.get("runtime", "python"),
                )

            except asyncio.TimeoutError:
                raise SandboxExecutionError(f"Command timed out after {timeout_seconds} seconds")
            except Exception as e:
                raise SandboxExecutionError(f"Local process fallback failed: {str(e)}")

        else:
            # Requirement 11: Host process fallback disallowed
            raise SandboxExecutionError("Container client unavailable and host fallback is disabled.")

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        """
        Reads file contents within the sandbox workspace boundary.
        Requirements 6, 11, 20
        """
        if sandbox_id not in self._sandboxes:
            raise SandboxExecutionError(f"Sandbox '{sandbox_id}' not found")

        sandbox_info = self._sandboxes[sandbox_id]
        workdir = sandbox_info["workdir"]
        session_id = sandbox_info["session_id"]

        try:
            abs_path = SandboxSecurityPolicy.validate_workspace_relative_path(workdir, file_path)
        except SecurityPolicyError as spe:
            audit_logger.record_event(
                SandboxAuditRecord(
                    event_id=uuid.uuid4().hex,
                    event_type=SandboxAuditEventType.SECURITY_VIOLATION,
                    sandbox_id=sandbox_id,
                    session_id=session_id,
                    file_path=file_path,
                    details={"error": str(spe)},
                )
            )
            raise SandboxExecutionError(str(spe))

        if not os.path.exists(abs_path):
            raise SandboxExecutionError(f"File not found: '{file_path}'")

        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        audit_logger.record_event(
            SandboxAuditRecord(
                event_id=uuid.uuid4().hex,
                event_type=SandboxAuditEventType.FILE_READ,
                sandbox_id=sandbox_id,
                session_id=session_id,
                file_path=file_path,
            )
        )
        return content

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        """
        Writes file contents inside the sandbox workspace boundary.
        Requirements 6, 11, 20
        """
        if sandbox_id not in self._sandboxes:
            raise SandboxExecutionError(f"Sandbox '{sandbox_id}' not found")

        sandbox_info = self._sandboxes[sandbox_id]
        workdir = sandbox_info["workdir"]
        session_id = sandbox_info["session_id"]

        try:
            abs_path = SandboxSecurityPolicy.validate_workspace_relative_path(workdir, file_path)
        except SecurityPolicyError as spe:
            audit_logger.record_event(
                SandboxAuditRecord(
                    event_id=uuid.uuid4().hex,
                    event_type=SandboxAuditEventType.SECURITY_VIOLATION,
                    sandbox_id=sandbox_id,
                    session_id=session_id,
                    file_path=file_path,
                    details={"error": str(spe)},
                )
            )
            raise SandboxExecutionError(str(spe))

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        audit_logger.record_event(
            SandboxAuditRecord(
                event_id=uuid.uuid4().hex,
                event_type=SandboxAuditEventType.FILE_WRITTEN,
                sandbox_id=sandbox_id,
                session_id=session_id,
                file_path=file_path,
            )
        )
        return True

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """
        Terminates container and cleans up temporary workspace.
        Requirements 10, 19, 20
        """
        if sandbox_id not in self._sandboxes:
            return False

        sandbox_info = self._sandboxes.pop(sandbox_id)
        container_id = sandbox_info.get("container_id")
        workdir = sandbox_info.get("workdir")
        session_id = sandbox_info.get("session_id", "unknown")

        if container_id and self.docker_client:
            try:
                container = self.docker_client.containers.get(container_id)
                container.stop(timeout=1)
                container.remove(force=True)
                logger.info("Sandbox container destroyed", sandbox_id=sandbox_id, container_id=container_id[:12])
            except Exception as e:
                logger.warning("Error stopping container during sandbox destroy", container_id=container_id, error=str(e))

        if workdir and os.path.exists(workdir):
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception as e:
                logger.warning("Error removing workspace dir", workdir=workdir, error=str(e))

        audit_logger.record_event(
            SandboxAuditRecord(
                event_id=uuid.uuid4().hex,
                event_type=SandboxAuditEventType.SANDBOX_DESTROYED,
                sandbox_id=sandbox_id,
                session_id=session_id,
            )
        )
        return True

    async def destroy_all_sandboxes(self):
        """Clean up all active sandboxes."""
        sandbox_ids = list(self._sandboxes.keys())
        for sb_id in sandbox_ids:
            await self.destroy_sandbox(sb_id)
