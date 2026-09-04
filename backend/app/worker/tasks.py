"""Worker tasks.

Two responsibilities:

* ``run_agent_session`` - execute one full agent run out-of-process. Self
  contained: it creates its own sandbox, provider and state machine, and always
  tears the sandbox down.
* ``reap_orphaned_sandboxes`` - periodic garbage collection for ``sb_*``
  containers and temp workspaces stranded by crashes, OOM kills or restarts.

Each prefork child lazily builds its own ``DockerSandboxAdapter`` (a Docker
client must not be shared across a fork) and registers it for teardown via the
``worker_process_shutdown`` signal in ``celery_app``.
"""

import asyncio
import os
import shutil
import tempfile
import time
from typing import Any, Dict, Optional

from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.core.logging import logger
from app.domain.entities.human_approval import ExecutionMode
from app.worker.celery_app import celery_app

# Container name prefix written by DockerSandboxAdapter.create_sandbox
# (f"sb_{session_id}_{uuid8}"), and the temp subdirectory it uses.
SANDBOX_NAME_PREFIX = "sb_"
SANDBOX_TEMP_SUBDIR = "agent_sandboxes"

# Per-process adapter. Created inside the child, never in the parent.
_adapter = None
_adapter_pid: Optional[int] = None


def _get_adapter():
    """Return this process's sandbox adapter, creating it on first use.

    Keyed on PID so a forked child never reuses the parent's Docker socket.
    """
    global _adapter, _adapter_pid
    from app.infrastructure.sandbox.docker_sandbox import DockerSandboxAdapter

    pid = os.getpid()
    if _adapter is None or _adapter_pid != pid:
        _adapter = DockerSandboxAdapter()
        _adapter_pid = pid
    return _adapter


async def shutdown_process_sandboxes() -> None:
    """Destroy every sandbox this process owns. Called on child shutdown."""
    global _adapter
    if _adapter is None:
        return
    await _adapter.destroy_all_sandboxes()
    _adapter = None


@celery_app.task(
    bind=True,
    name="app.worker.tasks.run_agent_session",
    # Agent runs are expensive and non-idempotent (they mutate a workspace and
    # spend provider tokens), so a failure is surfaced rather than retried
    # blindly. Retry is a deliberate operator decision.
    autoretry_for=(),
    max_retries=0,
)
def run_agent_session(
    self,
    session_id: str,
    user_prompt: str,
    project_id: str,
    initiator_id: str,
    ai_provider: str = "anthropic",
    model_name: str = "claude-3-5-sonnet-20241022",
    execution_mode: str = "APPROVAL_REQUIRED",
    max_iterations: int = 15,
) -> Dict[str, Any]:
    """Run one agent session to completion inside the worker process."""
    logger.info(
        "Worker accepted agent run",
        session_id=session_id,
        project_id=project_id,
        provider=ai_provider,
        model=model_name,
        celery_task_id=self.request.id,
    )
    return asyncio.run(
        _run_agent_session_async(
            session_id=session_id,
            user_prompt=user_prompt,
            project_id=project_id,
            initiator_id=initiator_id,
            ai_provider=ai_provider,
            model_name=model_name,
            execution_mode=execution_mode,
            max_iterations=max_iterations,
        )
    )


async def _run_agent_session_async(
    session_id: str,
    user_prompt: str,
    project_id: str,
    initiator_id: str,
    ai_provider: str,
    model_name: str,
    execution_mode: str,
    max_iterations: int,
) -> Dict[str, Any]:
    from app.application.agent.state_machine import AgentStateMachine
    from app.infrastructure.ai_providers.provider_factory import AIProviderFactory

    adapter = _get_adapter()
    mode = (
        ExecutionMode(execution_mode)
        if execution_mode in ExecutionMode.__members__
        else ExecutionMode.APPROVAL_REQUIRED
    )

    provider = AIProviderFactory.get_provider(ai_provider)
    sandbox_id = await adapter.create_sandbox(session_id, workspace_path="")

    try:
        machine = AgentStateMachine(
            task_id=session_id,
            user_prompt=user_prompt,
            provider=provider,
            sandbox=adapter,
            sandbox_id=sandbox_id,
            execution_mode=mode,
            initiator_id=initiator_id,
            provider_name=ai_provider,
            model_name=model_name,
        )
        await machine.run_autonomous_loop()
        logger.info(
            "Agent run finished",
            session_id=session_id,
            final_state=machine.run.state.value,
            iterations=machine.run.current_iteration,
        )
        return {
            "session_id": session_id,
            "state": machine.run.state.value,
            "high_risk_flagged": machine.run.high_risk_flagged,
            "execution_summary": machine.run.execution_summary,
        }
    except SoftTimeLimitExceeded:
        # Soft limit fires inside the task so this finally-block still runs.
        logger.error("Agent run exceeded soft time limit", session_id=session_id)
        raise
    finally:
        # Always reclaim the container and its temp workspace, including on
        # failure or timeout.
        try:
            await adapter.destroy_sandbox(sandbox_id)
        except Exception as exc:
            logger.error("Failed to destroy sandbox after run", sandbox_id=sandbox_id, error=str(exc))


@celery_app.task(name="app.worker.tasks.reap_orphaned_sandboxes")
def reap_orphaned_sandboxes() -> Dict[str, int]:
    """Remove sandbox containers and temp workspaces older than the orphan TTL.

    Sandboxes are normally destroyed by whoever created them. This catches the
    cases where that never happens: SIGKILL, OOM kill, node reboot, or a deploy
    that replaced the process mid-run. Without it, ``sb_*`` containers and
    ``<tmp>/agent_sandboxes/*`` directories accumulate until the host fills up.
    """
    import docker

    ttl = settings.SANDBOX_ORPHAN_TTL_SECONDS
    removed_containers = 0
    removed_dirs = 0
    now = time.time()

    # --- Containers ---------------------------------------------------------
    try:
        client = docker.from_env()
        for container in client.containers.list(all=True):
            name = container.name or ""
            if not name.startswith(SANDBOX_NAME_PREFIX):
                continue
            created_raw = container.attrs.get("Created", "")
            age = _age_seconds(created_raw, now)
            if age is None or age < ttl:
                continue
            try:
                container.remove(force=True)
                removed_containers += 1
                logger.info(
                    "Reaped orphaned sandbox container",
                    container_name=name,
                    age_seconds=int(age),
                )
            except Exception as exc:
                logger.warning("Could not remove sandbox container", container_name=name, error=str(exc))
    except Exception as exc:
        logger.warning("Sandbox container reaping skipped, Docker unreachable", error=str(exc))

    # --- Temp workspaces ----------------------------------------------------
    root = os.path.join(tempfile.gettempdir(), SANDBOX_TEMP_SUBDIR)
    if os.path.isdir(root):
        for entry in os.listdir(root):
            path = os.path.join(root, entry)
            if not os.path.isdir(path):
                continue
            try:
                if (now - os.path.getmtime(path)) < ttl:
                    continue
                shutil.rmtree(path, ignore_errors=True)
                removed_dirs += 1
                logger.info("Reaped orphaned sandbox workspace", path=path)
            except OSError as exc:
                logger.warning("Could not remove sandbox workspace", path=path, error=str(exc))

    if removed_containers or removed_dirs:
        logger.info(
            "Sandbox reaping complete",
            containers_removed=removed_containers,
            workspaces_removed=removed_dirs,
            ttl_seconds=ttl,
        )
    return {"containers_removed": removed_containers, "workspaces_removed": removed_dirs}


def _age_seconds(docker_created: str, now: float) -> Optional[float]:
    """Age in seconds from Docker's RFC3339 ``Created`` string, or None."""
    if not docker_created:
        return None
    from datetime import datetime, timezone

    try:
        # Docker returns nanosecond precision, which fromisoformat rejects on
        # Python < 3.11 and still dislikes beyond microseconds; trim to 6 digits.
        text = docker_created.replace("Z", "+00:00")
        if "." in text:
            head, _, tail = text.partition(".")
            frac, sign, offset = _split_offset(tail)
            text = f"{head}.{frac[:6]}{sign}{offset}"
        created = datetime.fromisoformat(text)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return now - created.timestamp()
    except (ValueError, TypeError):
        return None


def _split_offset(tail: str):
    for sign in ("+", "-"):
        if sign in tail:
            frac, _, offset = tail.partition(sign)
            return frac, sign, offset
    return tail, "", ""
