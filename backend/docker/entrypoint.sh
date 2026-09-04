#!/bin/sh
#
# Backend container entrypoint. Shared by the api, worker, beat and migrate
# services; behaviour is driven entirely by environment variables.
#
#   WAIT_FOR_POSTGRES=1        block until POSTGRES_SERVER:POSTGRES_PORT accepts TCP
#   WAIT_FOR_REDIS=1           block until REDIS_HOST:REDIS_PORT accepts TCP
#   WAIT_TIMEOUT=60            seconds to wait before giving up (exit 1)
#   ALEMBIC_UPGRADE_ON_START=1 run `alembic upgrade head` before starting
#
# Always ends in `exec "$@"` so the real process becomes PID 1 of the container
# and receives SIGTERM directly. Without exec, the shell would swallow the
# signal and Docker would SIGKILL the app after the grace period, defeating
# graceful shutdown.

set -eu

WAIT_TIMEOUT="${WAIT_TIMEOUT:-60}"

log() {
    # Timestamped, unbuffered, to stderr so it interleaves correctly with the
    # app's structured JSON logs on stdout.
    echo "[entrypoint] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >&2
}

# Wait for a TCP endpoint using Python's stdlib. Avoids adding netcat or
# postgresql-client to the runtime image just to poll a port.
wait_for_tcp() {
    host="$1"
    port="$2"
    label="$3"

    log "waiting up to ${WAIT_TIMEOUT}s for ${label} at ${host}:${port}"
    python - "$host" "$port" "$WAIT_TIMEOUT" "$label" <<'PY'
import socket
import sys
import time

host, port, timeout, label = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
deadline = time.monotonic() + timeout
last = ""
while time.monotonic() < deadline:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"[entrypoint] {label} is accepting connections", file=sys.stderr)
            sys.exit(0)
    except OSError as exc:
        last = str(exc)
        time.sleep(1)
print(f"[entrypoint] timed out waiting for {label} at {host}:{port} ({last})", file=sys.stderr)
sys.exit(1)
PY
}

if [ "${WAIT_FOR_POSTGRES:-0}" = "1" ]; then
    wait_for_tcp "${POSTGRES_SERVER:-postgres}" "${POSTGRES_PORT:-5432}" "PostgreSQL"
fi

if [ "${WAIT_FOR_REDIS:-0}" = "1" ]; then
    wait_for_tcp "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}" "Redis"
fi

# Schema migrations.
#
# Only ONE service should set this. Running it on every api/worker replica means
# concurrent `alembic upgrade head` calls racing on the same database. Alembic
# takes a lock on alembic_version so the race is usually survivable, but it is
# not something to rely on: use the dedicated `migrate` service instead, and
# leave ALEMBIC_UPGRADE_ON_START=0 everywhere else.
if [ "${ALEMBIC_UPGRADE_ON_START:-0}" = "1" ]; then
    log "applying database migrations (alembic upgrade head)"
    alembic upgrade head
    log "migrations applied; current revision:"
    alembic current >&2
fi

log "starting: $*"
exec "$@"
