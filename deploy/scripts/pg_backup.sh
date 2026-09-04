#!/bin/sh
###############################################################################
# PostgreSQL logical backup.
#
#   pg_backup.sh            take one backup and exit  (cron / manual / CI)
#   pg_backup.sh --loop     take one every BACKUP_SCHEDULE_SECONDS (container)
#
# Environment (standard libpq variables, so no credentials on the command line
# where `ps` would expose them):
#   PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD
#   BACKUP_DIR              default /backups
#   BACKUP_RETENTION_DAYS   default 14
#   BACKUP_SCHEDULE_SECONDS default 86400
#   BACKUP_S3_URI           optional, e.g. s3://bucket/agent-platform
#
# WHAT THIS DOES AND DOES NOT GIVE YOU
#   Custom-format dumps (-Fc) are compressed, parallel-restorable and allow
#   selective table restore. They are point-in-time only as of the moment the
#   dump started, so on the default daily schedule the worst-case data loss
#   (RPO) is 24 hours.
#   For a minutes-level RPO you need the WAL archive that compose.prod.yml
#   configures, replayed on top of a base backup. See docs/DEPLOYMENT.md
#   "Database recovery strategy".
#
#   A backup on the same host as the database is not disaster recovery: one disk
#   or host loss takes both. Set BACKUP_S3_URI, or otherwise copy off-host.
###############################################################################

set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_SCHEDULE_SECONDS="${BACKUP_SCHEDULE_SECONDS:-86400}"
PGDATABASE="${PGDATABASE:-agent_platform}"

log() {
    echo "[pg_backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

fail() {
    echo "[pg_backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*" >&2
    return 1
}

take_backup() {
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    base="${PGDATABASE}_${timestamp}"
    # Write to .partial first and rename only on success, so a crashed or
    # half-written dump can never be mistaken for a restorable backup.
    partial="${BACKUP_DIR}/${base}.dump.partial"
    final="${BACKUP_DIR}/${base}.dump"

    mkdir -p "$BACKUP_DIR"

    log "starting backup of ${PGDATABASE} on ${PGHOST:-localhost} -> $(basename "$final")"

    # -Fc  custom format: compressed, supports pg_restore -j and selective restore
    # --no-owner / --no-privileges  restorable into a database with different role
    #                               names, which is what makes restore-to-staging
    #                               work without recreating production roles
    if ! pg_dump \
            --format=custom \
            --compress=9 \
            --no-owner \
            --no-privileges \
            --verbose \
            --file="$partial" 2>/tmp/pg_dump.err; then
        log "pg_dump failed:"
        cat /tmp/pg_dump.err >&2
        rm -f "$partial"
        fail "backup aborted"
        return 1
    fi

    # Verify the dump is readable before trusting it. pg_restore --list parses the
    # archive's table of contents; if that fails, the file is corrupt. This is the
    # difference between having backups and having files.
    if ! pg_restore --list "$partial" >/dev/null 2>&1; then
        rm -f "$partial"
        fail "dump failed integrity verification (pg_restore --list); discarded"
        return 1
    fi

    mv "$partial" "$final"

    # Checksum for tamper/bit-rot detection, verified by pg_restore.sh.
    if command -v sha256sum >/dev/null 2>&1; then
        (cd "$BACKUP_DIR" && sha256sum "$(basename "$final")" > "$(basename "$final").sha256")
    fi

    size="$(du -h "$final" | cut -f1)"
    log "backup complete: $(basename "$final") (${size}), integrity verified"

    if [ -n "${BACKUP_S3_URI:-}" ]; then
        upload_offsite "$final"
    else
        log "WARNING: BACKUP_S3_URI is not set. This backup lives on the same host as the database and is not disaster recovery."
    fi
}

upload_offsite() {
    file="$1"
    if ! command -v aws >/dev/null 2>&1; then
        log "WARNING: BACKUP_S3_URI is set but the aws CLI is not installed in this image; skipping upload"
        return 0
    fi
    log "uploading $(basename "$file") to ${BACKUP_S3_URI}"
    if aws s3 cp "$file" "${BACKUP_S3_URI}/$(basename "$file")" --only-show-errors; then
        [ -f "${file}.sha256" ] && aws s3 cp "${file}.sha256" "${BACKUP_S3_URI}/$(basename "$file").sha256" --only-show-errors
        log "offsite upload complete"
    else
        # Do not fail the run: a local backup that exists is better than none.
        log "WARNING: offsite upload failed; the local backup was kept"
    fi
}

prune_old() {
    log "pruning backups older than ${BACKUP_RETENTION_DAYS} days"
    count=0
    # -mtime +N is whole days; find prints nothing if the directory is empty.
    for old in $(find "$BACKUP_DIR" -maxdepth 1 -name "*.dump" -type f -mtime "+${BACKUP_RETENTION_DAYS}" 2>/dev/null); do
        rm -f "$old" "${old}.sha256"
        log "pruned $(basename "$old")"
        count=$((count + 1))
    done
    [ "$count" -eq 0 ] && log "nothing to prune"

    remaining="$(find "$BACKUP_DIR" -maxdepth 1 -name '*.dump' -type f 2>/dev/null | wc -l | tr -d ' ')"
    log "${remaining} backup(s) retained in ${BACKUP_DIR}"

    # A retention policy that has silently deleted everything is worse than none.
    if [ "$remaining" -eq 0 ]; then
        log "WARNING: no backups remain after pruning; check BACKUP_RETENTION_DAYS and the backup schedule"
    fi
}

run_once() {
    take_backup
    prune_old
}

if [ "${1:-}" = "--loop" ]; then
    log "scheduler started: one backup every ${BACKUP_SCHEDULE_SECONDS}s, retaining ${BACKUP_RETENTION_DAYS} days"
    # Trap so `docker compose stop` does not leave a dump half-written; the
    # .partial rename already protects the archive, this just exits promptly.
    trap 'log "received termination signal, exiting"; exit 0' TERM INT

    while true; do
        # Never let one failed backup kill the scheduler: log it and try again on
        # the next tick.
        run_once || log "WARNING: backup cycle failed; retrying at the next interval"
        log "sleeping ${BACKUP_SCHEDULE_SECONDS}s until the next backup"
        sleep "$BACKUP_SCHEDULE_SECONDS" &
        wait $!
    done
else
    run_once
fi
