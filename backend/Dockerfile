# syntax=docker/dockerfile:1.7
###############################################################################
# Backend image - FastAPI API, Celery worker and Celery beat.
#
# All three run from the same image with different commands, so there is one
# artifact to build, scan, sign and promote. Build targets:
#
#   --target api           production ASGI server        (default)
#   --target worker        Celery worker / beat
#   --target migrate       one-shot `alembic upgrade head`
#   --target development   dev deps + hot reload
#
# Design notes
#   * Compilers live only in the builder stage. The runtime stage copies a
#     finished virtualenv, so gcc and friends are absent from the shipped image.
#   * Runs as an unprivileged user (uid 10001), never root.
#   * No secrets are referenced, copied or ARG-ed here. Configuration arrives as
#     environment variables at run time. `docker history` on this image reveals
#     nothing sensitive.
#   * git is deliberately not installed: the app never shells out to it
#     (app/infrastructure/vcs/local_git_provider.py routes git through the
#     sandbox), so it would only widen the attack surface.
###############################################################################

ARG PYTHON_VERSION=3.11
ARG APP_UID=10001
ARG APP_GID=10001
ARG SANDBOX_WORKSPACE_ROOT=/srv/agent/sandboxes


# =============================================================================
# Stage: python-base - shared interpreter settings for every later stage
# =============================================================================
FROM python:${PYTHON_VERSION}-slim AS python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app


# =============================================================================
# Stage: builder - compile wheels into a self-contained virtualenv
# =============================================================================
FROM python-base AS builder

# build-essential is needed for any dependency without a prebuilt manylinux
# wheel. It stays in this stage and is never copied forward.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV" \
    && pip install --upgrade pip setuptools wheel

# Copied on its own so the dependency layer is cached independently of source
# changes: editing application code does not trigger a reinstall.
COPY requirements.txt ./
RUN pip install -r requirements.txt


# =============================================================================
# Stage: builder-dev - builder plus test/dev tooling
# =============================================================================
FROM builder AS builder-dev

COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt


# =============================================================================
# Stage: runtime-base - minimal image, unprivileged user, application code
# =============================================================================
FROM python-base AS runtime-base

ARG APP_UID
ARG APP_GID
ARG SANDBOX_WORKSPACE_ROOT

# No package installs here: the runtime needs no compiler, no curl (the health
# check is a stdlib Python script) and no git.
RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin app

# Virtualenv from the builder - the only artifact carried across stages.
COPY --from=builder --chown=${APP_UID}:${APP_GID} /opt/venv /opt/venv

# Application code. .dockerignore keeps .venv, tests, __pycache__ and any .env
# out of the context entirely.
COPY --chown=${APP_UID}:${APP_GID} app ./app
COPY --chown=${APP_UID}:${APP_GID} alembic ./alembic
COPY --chown=${APP_UID}:${APP_GID} alembic.ini ./alembic.ini
COPY --chown=${APP_UID}:${APP_GID} prompts ./prompts
COPY --chown=${APP_UID}:${APP_GID} docker/entrypoint.sh docker/healthcheck.py /usr/local/bin/

# Strip CRLF (the repo is developed on Windows; a \r would make the kernel look
# for the interpreter "/bin/sh\r") and set the exec bit, which a Windows
# filesystem cannot carry.
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/healthcheck.py

# Fail the build - not a production request - if prompt templates are missing.
# PromptManager silently falls back to mkdir-ing an empty directory, which would
# leave every subagent running on empty prompts.
RUN test -f /app/prompts/manifest.json \
    || (echo "FATAL: backend/prompts/manifest.json missing from build context" >&2 && exit 1)

# Sandbox scratch root. Must match SANDBOX_WORKSPACE_ROOT/TMPDIR at run time and
# be owned by the app user, otherwise create_sandbox cannot write its workspace.
RUN mkdir -p "${SANDBOX_WORKSPACE_ROOT}" \
    && chown -R "${APP_UID}:${APP_GID}" "${SANDBOX_WORKSPACE_ROOT}"

USER ${APP_UID}:${APP_GID}

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]


# =============================================================================
# Stage: api - production ASGI server
# =============================================================================
FROM runtime-base AS api

EXPOSE 8000

# --workers 1 is a correctness requirement, not a performance choice.
#   Agent sessions (SESSIONS_DB / STATE_MACHINES_DB), the rate limiter and the
#   brute-force lockout counters are all plain in-process dicts. A second worker
#   would get its own copies, so a session created by one worker returns 404
#   from the other and rate limits would multiply by the worker count.
#   See docs/DEPLOYMENT.md "Scaling constraints".
#
# --timeout-graceful-shutdown gives the lifespan shutdown hook time to destroy
# sandbox containers and dispose the database pool. Keep it below the
# container's stop_grace_period.
#
# --proxy-headers + --forwarded-allow-ips make the app trust X-Forwarded-For and
# X-Forwarded-Proto from the reverse proxy. Only correct because nothing but the
# proxy can reach this port; do not publish it directly.
#
# --no-access-log suppresses uvicorn's own access line: ObservabilityMiddleware
# already emits one structured JSON record per request, and duplicating it
# doubles log volume and cost.
CMD ["sh", "-c", "exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --timeout-graceful-shutdown ${GRACEFUL_TIMEOUT:-30} \
    --no-server-header \
    --no-access-log"]

# start-period is generous: the process must import the app, run the settings
# validator and open a database connection before /readiness can pass.
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD ["python", "/usr/local/bin/healthcheck.py"]


# =============================================================================
# Stage: worker - Celery worker (also used for celery beat, command overridden)
# =============================================================================
FROM runtime-base AS worker

# Concurrency is intentionally low: every concurrent task holds a sandbox
# container, which itself consumes SANDBOX_MAX_CPUS and SANDBOX_MAX_MEMORY_MB.
# Effective host load is roughly concurrency x sandbox limits.
ENV CELERY_CONCURRENCY=2 \
    CELERY_LOGLEVEL=info

CMD ["sh", "-c", "exec celery -A app.worker.celery_app:celery_app worker \
    --loglevel=${CELERY_LOGLEVEL} \
    --concurrency=${CELERY_CONCURRENCY} \
    --max-tasks-per-child=${WORKER_MAX_TASKS_PER_CHILD:-20} \
    --without-gossip --without-mingle"]

# `inspect ping` round-trips through the broker, so this verifies the worker is
# both alive and able to reach Redis. -d targets only this container's node.
HEALTHCHECK --interval=60s --timeout=20s --start-period=45s --retries=3 \
    CMD ["sh", "-c", "celery -A app.worker.celery_app:celery_app inspect ping -d celery@$(hostname) >/dev/null 2>&1"]


# =============================================================================
# Stage: migrate - one-shot schema migration, exits when finished
# =============================================================================
FROM runtime-base AS migrate

ENV WAIT_FOR_POSTGRES=1 \
    WAIT_TIMEOUT=120

# Run in the foreground and exit with alembic's status so an orchestrator can
# gate the rollout on it (Compose: `service_completed_successfully`;
# Kubernetes: an init container or a Job).
CMD ["alembic", "upgrade", "head"]


# =============================================================================
# Stage: development - dev dependencies, hot reload, source bind-mounted
# =============================================================================
FROM python-base AS development

ARG APP_UID
ARG APP_GID
ARG SANDBOX_WORKSPACE_ROOT

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /bin/bash app

COPY --from=builder-dev --chown=${APP_UID}:${APP_GID} /opt/venv /opt/venv

# Source is bind-mounted over /app by the dev compose file, so this COPY only
# seeds the image for `docker run` without a mount.
COPY --chown=${APP_UID}:${APP_GID} . .

RUN sed -i 's/\r$//' docker/entrypoint.sh \
    && cp docker/entrypoint.sh docker/healthcheck.py /usr/local/bin/ \
    && chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/healthcheck.py \
    && mkdir -p "${SANDBOX_WORKSPACE_ROOT}" \
    && chown -R "${APP_UID}:${APP_GID}" "${SANDBOX_WORKSPACE_ROOT}" /app

USER ${APP_UID}:${APP_GID}

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD ["python", "/usr/local/bin/healthcheck.py"]
