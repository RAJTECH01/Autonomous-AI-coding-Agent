"""Celery application for the worker service.

Broker and result backend are both Redis, built from the same POSTGRES_*/REDIS_*
environment variables the API uses (``settings.REDIS_URL``). Redis therefore
holds queue state that must survive a restart, which is why the deployment
configures AOF persistence rather than running Redis as a pure cache.

WHAT THE WORKER DOES TODAY
  1. ``reap_orphaned_sandboxes`` runs on a beat schedule and removes ``sb_*``
     containers and temp workspaces left behind by crashed or restarted
     processes. This is active from the first deploy.
  2. ``run_agent_session`` can execute a full agent run out-of-process.

KNOWN GAP - read before assuming runs are queued
  ``POST /api/v1/sessions`` still executes agent runs *in-process* via FastAPI
  ``BackgroundTasks``, keeping ``AgentSession`` and ``AgentStateMachine`` in the
  module-level ``SESSIONS_DB``/``STATE_MACHINES_DB`` dicts in
  ``app/api/v1/endpoints/sessions.py``. Nothing enqueues ``run_agent_session``
  yet, because moving execution out of the API process requires a shared session
  store (PostgreSQL or Redis) so ``GET /api/v1/sessions/{id}`` can read status
  written by a different process. Until that lands, the agent-run queue has no
  producer and the reaper is the worker's only live job.
  See docs/DEPLOYMENT.md "Scaling constraints".
"""

from celery import Celery
from celery.signals import worker_process_shutdown, worker_shutting_down

from app.core.config import settings
from app.core.logging import logger, setup_logging

setup_logging()

celery_app = Celery(
    "agent_platform",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    # --- Serialization: JSON only. Never enable pickle; task payloads originate
    #     from user input and pickle deserialization is remote code execution.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # --- Delivery guarantees ------------------------------------------------
    # acks_late means a task is acknowledged only after it finishes, so a worker
    # killed mid-run redelivers instead of silently dropping the run.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Long tasks must not be hoarded: one child fetches one message at a time.
    worker_prefetch_multiplier=settings.WORKER_PREFETCH_MULTIPLIER,
    # --- Time limits --------------------------------------------------------
    task_soft_time_limit=settings.WORKER_TASK_SOFT_TIME_LIMIT_SECONDS,
    task_time_limit=settings.WORKER_TASK_TIME_LIMIT_SECONDS,
    # --- Memory hygiene -----------------------------------------------------
    worker_max_tasks_per_child=settings.WORKER_MAX_TASKS_PER_CHILD,
    # --- Startup resilience -------------------------------------------------
    # The worker container can start before Redis is accepting connections.
    broker_connection_retry_on_startup=True,
    result_expires=86400,
    task_track_started=True,
    # --- Beat schedule ------------------------------------------------------
    beat_schedule={
        "reap-orphaned-sandboxes": {
            "task": "app.worker.tasks.reap_orphaned_sandboxes",
            "schedule": float(settings.SANDBOX_REAPER_INTERVAL_SECONDS),
        },
    },
)


@worker_shutting_down.connect
def _on_worker_shutting_down(sig=None, how=None, exitcode=None, **kwargs):
    """Log the shutdown mode so warm vs cold stops are distinguishable in logs.

    A warm shutdown (SIGTERM, Celery's default) lets running agent runs finish
    up to the container's stop_grace_period. A cold shutdown (SIGQUIT) does not.
    """
    logger.info("Celery worker shutting down", signal=str(sig), how=str(how), exitcode=exitcode)


@worker_process_shutdown.connect
def _on_worker_process_shutdown(pid=None, exitcode=None, **kwargs):
    """Destroy this child's sandbox containers before the process dies.

    Each prefork child owns its own DockerSandboxAdapter (created lazily in
    app.worker.tasks). Without this hook, recycling a child via
    worker_max_tasks_per_child would leak its containers and temp workspaces.
    """
    import asyncio

    from app.worker.tasks import shutdown_process_sandboxes

    try:
        asyncio.run(shutdown_process_sandboxes())
    except Exception as exc:
        logger.error("Sandbox cleanup failed during worker process shutdown", pid=pid, error=str(exc))
