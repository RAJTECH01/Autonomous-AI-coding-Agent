#!/bin/sh
###############################################################################
# PostgreSQL restore.
#
#   pg_restore.sh --list
#   pg_restore.sh --file /backups/agent_platform_20260825T030000Z.dump [--yes]
#   pg_restore.sh --latest --target-db agent_platform_restore_check
#
# This script OVERWRITES the schema and data of the target database. It refuses
# to run without an explicit confirmation unless --yes is passed.
#
# Environment: PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD, BACKUP_DIR
#
# RECOVERY MODEL
#   This restores a logical dump: the database returns to the state captured when
#   that dump began. Anything written afterwards is gone. To recover to a point
#   in time between dumps, use the WAL archive instead - the procedure is in
#   docs/DEPLOYMENT.md "Database recovery strategy". This script cannot do PITR.
#
#   Rehearse restores. An unrehearsed backup is a hypothesis, not a recovery
#   plan; --target-db lets you rehearse into a scratch database safely, and the
#   CI pipeline exercises exactly that path.
###############################################################################

set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DUMP_FILE=""
TARGET_DB="${PGDATABASE:-agent_platform}"
ASSUME_YES=0
USE_LATEST=0
JOBS="${RESTORE_JOBS:-4}"

log() {
    echo "[pg_restore] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

die() {
    echo "[pg_restore] ERROR: $*" >&2
    exit 1
}

usage() {
    sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

list_backups() {
    log "backups available in ${BACKUP_DIR}:"
    found=0
    for f in "$BACKUP_DIR"/*.dump; do
        [ -e "$f" ] || continue
        found=1
        size="$(du -h "$f" | cut -f1)"
        printf '  %-52s %8s\n' "$(basename "$f")" "$size"
    done
    [ "$found" -eq 0 ] && log "(none found)"
}

latest_backup() {
    # Timestamped names sort lexicographically in chronological order.
    ls -1 "$BACKUP_DIR"/*.dump 2>/dev/null | sort | tail -n 1
}

verify_checksum() {
    file="$1"
    if [ ! -f "${file}.sha256" ]; then
        log "WARNING: no .sha256 companion for $(basename "$file"); integrity NOT verified"
        return 0
    fi
    command -v sha256sum >/dev/null 2>&1 || { log "WARNING: sha256sum unavailable; skipping checksum"; return 0; }

    log "verifying checksum"
    (cd "$(dirname "$file")" && sha256sum -c "$(basename "$file").sha256" >/dev/null) \
        || die "checksum mismatch for $(basename "$file"). The backup is corrupt or was tampered with; do not restore it."
    log "checksum OK"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --file)      DUMP_FILE="${2:?--file requires a path}"; shift 2 ;;
        --latest)    USE_LATEST=1; shift ;;
        --target-db) TARGET_DB="${2:?--target-db requires a name}"; shift 2 ;;
        --list)      list_backups; exit 0 ;;
        --yes|-y)    ASSUME_YES=1; shift ;;
        --jobs)      JOBS="${2:?--jobs requires a number}"; shift 2 ;;
        -h|--help)   usage 0 ;;
        *)           die "unknown argument: $1 (try --help)" ;;
    esac
done

if [ "$USE_LATEST" -eq 1 ]; then
    DUMP_FILE="$(latest_backup)"
    [ -n "$DUMP_FILE" ] || die "no backups found in ${BACKUP_DIR}"
    log "selected latest backup: $(basename "$DUMP_FILE")"
fi

[ -n "$DUMP_FILE" ] || die "specify --file <path> or --latest (see --list)"
[ -f "$DUMP_FILE" ] || die "no such file: $DUMP_FILE"

verify_checksum "$DUMP_FILE"

# Confirm the archive is intact and readable before touching the target.
pg_restore --list "$DUMP_FILE" >/dev/null 2>&1 \
    || die "$(basename "$DUMP_FILE") is not a valid custom-format dump"

cat <<BANNER

  ================ DESTRUCTIVE OPERATION ================
  Source dump : $(basename "$DUMP_FILE")
  Target host : ${PGHOST:-localhost}:${PGPORT:-5432}
  Target DB   : ${TARGET_DB}

  Every table in the target database will be DROPPED and
  recreated from the dump. Data written after the dump was
  taken will be LOST.

  Stop the application first, or it will write into a
  database that is being rebuilt underneath it.
  =======================================================

BANNER

if [ "$ASSUME_YES" -ne 1 ]; then
    printf 'Type the target database name (%s) to proceed: ' "$TARGET_DB"
    read -r reply
    [ "$reply" = "$TARGET_DB" ] || die "confirmation did not match; aborted"
fi

log "restoring into ${TARGET_DB} with ${JOBS} parallel jobs"

# --clean --if-exists  drop existing objects first, tolerating absent ones
# --no-owner --no-privileges  match how the dump was taken
# --exit-on-error  stop at the first failure instead of leaving a half-restored
#                  database that looks like it worked
if pg_restore \
        --dbname="$TARGET_DB" \
        --clean --if-exists \
        --no-owner --no-privileges \
        --jobs="$JOBS" \
        --exit-on-error \
        --verbose \
        "$DUMP_FILE"; then
    log "restore completed successfully"
else
    die "restore FAILED. The target database is in an inconsistent state; do not start the application against it."
fi

# Post-restore sanity checks. A restore that "succeeded" but produced no tables,
# or left the schema at the wrong migration, must not be reported as good.
log "verifying restored schema"

table_count="$(psql --dbname="$TARGET_DB" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
log "public tables restored: ${table_count}"
[ "$table_count" -gt 0 ] || die "restore produced zero tables in the public schema"

if psql --dbname="$TARGET_DB" -tAc \
        "SELECT to_regclass('public.alembic_version') IS NOT NULL" | grep -q '^t$'; then
    revision="$(psql --dbname="$TARGET_DB" -tAc 'SELECT version_num FROM alembic_version')"
    log "alembic revision in restored database: ${revision}"
    log "NEXT STEP: run 'alembic upgrade head' if the deployed code expects a newer revision"
else
    log "WARNING: no alembic_version table found. This dump predates migration tracking, or the schema is incomplete."
fi

log "done"
