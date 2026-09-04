#!/usr/bin/env bash
###############################################################################
# End-to-end smoke test against the production image targets.
#
#   deploy/scripts/smoke_test.sh
#
# Builds the production Dockerfile targets, boots the full stack from
# deploy/compose.ci.yml, verifies it with deploy/scripts/health_check.sh, then
# tears everything down. Used by the pull-request pipeline and runnable locally.
#
# Exit code 0 only if every service became healthy AND every health assertion
# passed. On failure it dumps per-service logs before cleaning up, because a CI
# failure with no logs costs another full run to diagnose.
#
# Environment
#   KEEP_UP=1        leave the stack running after the test (local debugging)
#   BASE_URL         override the URL under test (default http://localhost:8080)
#   TIMEOUT          seconds to wait for readiness (default 180)
###############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${DEPLOY_DIR}/compose.ci.yml"
PROJECT_NAME="agent-smoke-$$"

BASE_URL="${BASE_URL:-http://localhost:8080}"
TIMEOUT="${TIMEOUT:-180}"
KEEP_UP="${KEEP_UP:-0}"

# Sandbox workspace root must exist on the host at the same absolute path the
# containers use, so nested sandbox bind mounts resolve to the same directory.
SANDBOX_ROOT="/tmp/agent-sandboxes"

compose() {
    docker compose --project-name "$PROJECT_NAME" --file "$COMPOSE_FILE" "$@"
}

log() { echo ""; echo "==> $*"; }

dump_diagnostics() {
    log "DIAGNOSTICS: service state"
    compose ps || true

    log "DIAGNOSTICS: per-service logs"
    for svc in migrate backend worker frontend reverse-proxy postgres redis sandbox-broker; do
        echo ""
        echo "--------- ${svc} ---------"
        compose logs --no-color --tail=120 "$svc" 2>&1 || echo "(no logs for ${svc})"
    done

    log "DIAGNOSTICS: container health status"
    # Health status lives on the container, not in `compose ps` output detail.
    for cid in $(compose ps -q 2>/dev/null); do
        name="$(docker inspect --format '{{.Name}}' "$cid" 2>/dev/null || echo '?')"
        health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo '?')"
        exitcode="$(docker inspect --format '{{.State.ExitCode}}' "$cid" 2>/dev/null || echo '?')"
        echo "  ${name}: health=${health} exit=${exitcode}"
    done
}

cleanup() {
    local status=$?
    if (( status != 0 )); then
        dump_diagnostics
    fi

    if [[ "$KEEP_UP" == "1" ]]; then
        log "KEEP_UP=1: leaving the stack running as project ${PROJECT_NAME}"
        echo "    inspect : docker compose -p ${PROJECT_NAME} -f ${COMPOSE_FILE} ps"
        echo "    tear down: docker compose -p ${PROJECT_NAME} -f ${COMPOSE_FILE} down -v"
    else
        log "tearing down"
        # -v removes volumes, --remove-orphans catches renamed services so a CI
        # runner is never left with leftover containers.
        compose down --volumes --remove-orphans --timeout 20 >/dev/null 2>&1 || true
        # Sandbox containers are started by the app through the Docker API, so
        # Compose does not know about them and `down` will not remove them.
        docker ps -aq --filter "name=^sb_" 2>/dev/null | xargs -r docker rm -f >/dev/null 2>&1 || true
        rm -rf "${SANDBOX_ROOT}" 2>/dev/null || true
    fi

    exit "$status"
}
trap cleanup EXIT

log "preparing sandbox workspace root at ${SANDBOX_ROOT}"
mkdir -p "$SANDBOX_ROOT"
# The backend and worker run as uid 10001 and must be able to write here.
chmod 777 "$SANDBOX_ROOT"

log "building production image targets"
compose build --progress plain

log "starting the stack"
# The migrate service must exit 0 before backend/worker start; `up` honours the
# service_completed_successfully condition, so a failed migration fails here.
compose up --detach --wait --wait-timeout "$TIMEOUT"

log "stack is up; service state:"
compose ps

log "confirming migrations applied cleanly"
migrate_exit="$(docker inspect --format '{{.State.ExitCode}}' \
    "$(compose ps -aq migrate)" 2>/dev/null || echo "unknown")"
if [[ "$migrate_exit" != "0" ]]; then
    echo "ERROR: the migrate service exited with ${migrate_exit}, expected 0" >&2
    exit 1
fi
echo "    migrate exited 0"

log "verifying the alembic revision matches the code"
# Guards against a migration that applied but left the database on an older
# revision than the shipped code expects.
compose run --rm --no-deps \
    -e WAIT_FOR_POSTGRES=1 \
    migrate alembic current 2>&1 | tail -5

log "running health checks against ${BASE_URL}"
BASE_URL="$BASE_URL" TIMEOUT="$TIMEOUT" bash "${SCRIPT_DIR}/health_check.sh"

log "verifying the worker is connected to the broker"
# Proves the Celery worker booted, reached Redis and registered its tasks.
if compose exec -T worker celery -A app.worker.celery_app:celery_app inspect ping 2>&1 | grep -q "pong"; then
    echo "    worker responded to inspect ping"
else
    echo "ERROR: the Celery worker did not answer inspect ping" >&2
    compose logs --no-color --tail=60 worker >&2
    exit 1
fi

log "verifying the periodic reaper task is registered"
if compose exec -T worker celery -A app.worker.celery_app:celery_app inspect registered 2>&1 \
        | grep -q "app.worker.tasks.reap_orphaned_sandboxes"; then
    echo "    reap_orphaned_sandboxes is registered"
else
    echo "ERROR: expected task reap_orphaned_sandboxes was not registered" >&2
    exit 1
fi

log "verifying containers do not run as root"
# Requirement: non-root containers. Asserted at runtime rather than trusted from
# the Dockerfile, since a compose `user:` override could undo it.
for svc in backend worker frontend reverse-proxy; do
    uid="$(compose exec -T "$svc" id -u 2>/dev/null | tr -d '\r\n' || echo "unknown")"
    if [[ "$uid" == "0" ]]; then
        echo "ERROR: service ${svc} is running as root (uid 0)" >&2
        exit 1
    fi
    echo "    ${svc} runs as uid ${uid}"
done

log "SMOKE TEST PASSED"
