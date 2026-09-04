# Production Deployment Specification

Autonomous AI Coding Agent Platform — container deployment architecture.

---

## 1. Read this first: what Docker Compose is and is not

This specification uses Docker Compose to run production. **Docker Compose alone is
not a complete production orchestration solution.** It is a single-host container
runtime with a convenient configuration format. Treating it as an orchestrator
means accepting the following, knowingly:

| Missing capability | Consequence here |
| --- | --- |
| Multi-node scheduling | Everything runs on one host. That host is a single point of failure. |
| Rolling deploys gated on health | `up -d` replaces containers with a short interruption. There is no gradual shift of traffic and no automatic halt partway through. |
| Automatic rescheduling | If the host dies, nothing moves it. Recovery is manual. |
| Horizontal autoscaling | Replica counts are static values in a file. |
| Secret management | Secrets are environment variables from a file on disk, not a versioned store with rotation and audit. |
| Built-in service mesh / mTLS | Traffic between containers is plaintext on a bridge network. |
| Cluster-level RBAC | Anyone who can reach the Docker socket on the host is effectively root. |

This architecture is appropriate for **a single-node production deployment, a
staging environment, or an internal deployment with a tolerated maintenance
window.** If you need zero-downtime deploys, more than one node, or automatic
failover, move the same images to Kubernetes, ECS or Nomad. The images,
entrypoints, health checks, migration job and configuration surface were all built
to port directly: the container contract does not change, only the thing that
schedules it. Section 14 lists what to translate.

---

## 2. Architecture

```
                          Internet
                             │
                    ┌────────▼─────────┐
                    │  reverse-proxy   │  TLS termination, rate limiting,
                    │  nginx (uid 101) │  security headers, routing
                    │  :80/:443        │  THE ONLY PUBLISHED PORTS
                    └────┬────────┬────┘
                 /       │        │
        ┌────────▼───┐   │   ┌────▼─────────┐
        │  frontend  │   │   │   backend    │
        │  nginx     │   │   │  FastAPI     │
        │  :8080     │   │   │  :8000       │
        │  static    │   │   │  uid 10001   │
        └────────────┘   │   └──┬────────┬──┘
                         │      │        │
      ═══ edge network ══╧══════╧════    │
                                         │
      ═══ data network (internal) ═══════╪═══════════════
              │                │         │              │
       ┌──────▼─────┐   ┌──────▼────┐    │      ┌───────▼──────┐
       │ postgres   │   │  redis    │    │      │   worker     │
       │ :5432      │   │  :6379    │◄───┼──────┤   celery     │
       │ WAL archive│   │  AOF      │    │      │   uid 10001  │
       └──────┬─────┘   └───────────┘    │      └───────┬──────┘
              │                          │              │
       ┌──────▼─────┐              ┌─────▼──────┐       │
       │ pg-backup  │              │   beat     │       │
       │ pg_dump    │              │  scheduler │       │
       └────────────┘              └────────────┘       │
                                                        │
      ═══ sandbox network (internal) ════════════════════╧═══
                             │
                    ┌────────▼─────────┐
                    │  sandbox-broker  │  filtered Docker API
                    │  :2375           │
                    └────────┬─────────┘
                             │ /var/run/docker.sock
                    ┌────────▼─────────┐
                    │  sandbox         │  ephemeral, network=none,
                    │  containers      │  read-only, caps dropped
                    │  sb_<session>_*  │
                    └──────────────────┘
```

Three networks, deliberately segmented. `data` and `sandbox` are `internal: true`,
so they have **no route to the internet at all** — a compromised database or
broker container cannot exfiltrate outbound. The reverse proxy sits only on `edge`,
so a proxy compromise cannot reach PostgreSQL, Redis or the Docker broker.

### Services

| Service | Image | User | Published | Health check | CPU / Mem limit | Restart |
| --- | --- | --- | --- | --- | --- | --- |
| `reverse-proxy` | built from `deploy/reverse-proxy` | 101 | **80, 443** | `GET /healthz` | 1.0 / 256M | unless-stopped |
| `frontend` | built from `frontend`, target `production` | 101 | none | `GET /healthz` | 0.5 / 128M | unless-stopped |
| `backend` | built from `backend`, target `api` | 10001 | none | `healthcheck.py` → `/api/v1/readiness` | 2.0 / 2G | unless-stopped |
| `worker` | built from `backend`, target `worker` | 10001 | none | `celery inspect ping` | 2.0 / 2G | unless-stopped |
| `beat` | same as worker | 10001 | none | — (singleton scheduler) | 0.5 / 256M | unless-stopped |
| `postgres` | `postgres:15-alpine` | postgres | none | `pg_isready -U … -d …` | 2.0 / 2G | unless-stopped |
| `redis` | `redis:7-alpine` | redis | none | `redis-cli ping` | 1.0 / 768M | unless-stopped |
| `sandbox-broker` | `tecnativa/docker-socket-proxy:0.2.0` | root¹ | none | `GET /_ping` | 0.5 / 128M | unless-stopped |
| `migrate` | backend api image | 10001 | none | one-shot, must exit 0 | 1.0 / 512M | **no** |
| `postgres-init` | `postgres:15-alpine` | root² | none | one-shot | — | **no** |
| `pg-backup` | `postgres:15-alpine` | postgres | none | — | 1.0 / 512M | unless-stopped |

¹ The socket proxy requires access to the Docker socket; this is inherent to its
purpose. It is the only container with that access.
² Runs `chown` on two volumes, then exits. Explained in section 9.

Every application container also gets `cap_drop: ALL`, `no-new-privileges:true`,
`read_only: true` and an explicit `tmpfs` for `/tmp`. PostgreSQL is the documented
exception to `cap_drop`: its entrypoint starts as root to fix data-directory
ownership and needs `CAP_CHOWN`/`CAP_SETUID`/`CAP_SETGID` to drop privileges.

---

## 3. Requirement traceability

| # | Requirement | Where it is implemented |
| --- | --- | --- |
| 1 | Multi-stage builds | `backend/Dockerfile` (7 stages), `frontend/Dockerfile` (4), `deploy/reverse-proxy/Dockerfile` |
| 2 | Minimal runtime images | Compilers confined to `builder`; runtime copies only `/opt/venv`. No `git`, no `curl`, no `gcc`. Frontend runtime has no Node.js and no `node_modules`. |
| 3 | Non-root containers | uid 10001 (backend/worker/beat), uid 101 (nginx). Asserted at runtime by `smoke_test.sh` and in CI by inspecting `.Config.User`. |
| 4 | Health checks | `HEALTHCHECK` in every image; `depends_on: condition: service_healthy` gates startup order. |
| 5 | Resource limits | `deploy.resources.limits` + `reservations` per service in `compose.prod.yml`. |
| 6 | Environment-based configuration | All config via env vars consumed by `app/core/config.py`. `.env.example` documents every key. |
| 7 | No secrets in Dockerfiles | No secret-bearing `ARG`/`ENV` anywhere; CI asserts this with a grep gate. |
| 8 | No secrets in Git | `.gitignore` excludes `.env`, keys and certs. CI runs gitleaks over full history and asserts no `.env` is tracked. |
| 9 | Separate dev / prod configs | `docker-compose.yml` (dev), `deploy/compose.prod.yml` (prod), `deploy/compose.ci.yml` (CI). |
| 10 | Persistent PostgreSQL storage | Named volume `agent-postgres-data` + separate WAL archive volume. |
| 11 | Redis persistence | `deploy/redis/redis.conf`: AOF `everysec` + RDB snapshots, `maxmemory-policy noeviction`. |
| 12 | Automated migrations | `migrate` service runs `alembic upgrade head`; `depends_on: service_completed_successfully` blocks the API until it succeeds. |
| 13 | Graceful shutdown | Lifespan hook in `app/main.py`; `exec` in the entrypoint; `stop_grace_period` per service; `SIGQUIT` for nginx. |
| 14 | Restart policies | `unless-stopped` for long-running services, `"no"` for one-shot jobs. |
| 15 | Log management | `json-file` with `max-size`/`max-file`/`compress` on every service; structured JSON from both app and proxy. |
| 16 | Backup strategy | `pg-backup` service + `deploy/scripts/pg_backup.sh`, with integrity verification and retention. |
| 17 | Database recovery | `deploy/scripts/pg_restore.sh` + WAL archiving for PITR. Section 10. |

---

## 4. Configuration and secrets

Configuration is entirely environment-driven. `app/core/config.py` defines the
surface; `.env.example` documents it.

### Setup

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
chmod 600 .env
```

### Fail-fast validation

`Settings._enforce_production_hardening` raises at **import time** — before uvicorn
binds a port — when `ENVIRONMENT` is outside `{development, test, local}` and any of
these hold:

- `SECRET_KEY` is still the development default, or shorter than 32 characters
- `DEBUG` is true
- `SANDBOX_ALLOW_HOST_FALLBACK` is true

The failure mode is an immediate non-zero exit, which the health check turns into a
failed rollout rather than a running-but-insecure service. This is intentional.

### Two traps worth knowing

**Do not copy `.env` to `backend/.env`.** `Settings` uses
`SettingsConfigDict(env_file=".env", extra="forbid")`. pydantic reads *every* key
from a dotenv file and rejects keys that are not fields, so a `backend/.env`
containing deployment-only keys (`DOCKER_HOST`, `TAG`, `BACKUP_*`) crashes the app
at import. Environment variables are matched only against declared fields, so the
Compose `env_file` path used here is safe.

**`ALLOWED_ORIGINS` is JSON, not a comma list.** It is a `List[str]`, so
pydantic parses it as JSON:
`ALLOWED_ORIGINS=["https://agent.example.com"]`.

### Secrets inventory

| Secret | Consumer | Rotation |
| --- | --- | --- |
| `SECRET_KEY` | JWT signing | Rotating invalidates all active sessions |
| `POSTGRES_PASSWORD` | backend, worker, migrate, pg-backup | Requires coordinated restart |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | AI providers | Rotate at the provider, then restart |
| TLS `privkey.pem` | reverse-proxy | Mounted read-only, never in an image |

Compose reads these from a file on disk. That is the weakest part of this
architecture; a secret store with versioning and audit is the upgrade path.

---

## 5. Build reproducibility

`backend/requirements.txt` uses open-ended `>=` specifiers, so two builds of the
same commit can resolve different dependency versions. Before treating a build as
reproducible:

```bash
cd backend
pip install pip-tools
pip-compile --generate-hashes -o requirements.lock requirements.txt
# then in the Dockerfile builder stage:
#   pip install --require-hashes -r requirements.lock
```

The frontend is already reproducible: the Dockerfile uses `npm ci` against
`package-lock.json`, which fails if the lockfile and `package.json` disagree.

Release images are addressed **by digest**, not by tag. `compose.prod.yml` requires
`BACKEND_API_IMAGE`, `BACKEND_WORKER_IMAGE`, `FRONTEND_IMAGE` and
`REVERSE_PROXY_IMAGE` to be set (`${VAR:?message}`), so `up -d` fails fast rather
than silently resolving a mutable tag. The release pipeline writes them into
`deployment-manifest.env`.

---

## 6. Sandbox execution service

The sandbox is not a separate application service. `DockerSandboxAdapter` is an
in-process library that talks to a Docker daemon through `docker.from_env()`, which
means the connection is controlled entirely by `DOCKER_HOST`.

The deployment-level service is therefore an **API broker**: `sandbox-broker` is
the only container with the host Docker socket mounted, and the backend and worker
reach it over TCP on an internal network. The proxy allowlists only what the
adapter needs:

| Permission | Why |
| --- | --- |
| `CONTAINERS=1` | create, inspect, remove sandbox containers |
| `POST=1` | without it the proxy is read-only and nothing works |
| `EXEC=1` | `container.exec_run` — how commands reach the sandbox |
| `IMAGES=1` | pull `python:3.11-slim` etc. on first use |
| `VERSION=1`, `PING=1`, `INFO=1` | client initialisation and negotiation |

Everything else — `NETWORKS`, `VOLUMES`, `SWARM`, `SECRETS`, `CONFIGS`, `NODES`,
`SERVICES`, `BUILD` — is explicitly `0`.

### Residual risk, stated plainly

**This narrows the blast radius; it is not equivalent to real isolation.**
`CONTAINERS=1` plus `POST=1` plus `EXEC=1` is enough to create a container that
bind-mounts the host filesystem. An attacker with code execution inside the backend
or worker can use this endpoint to escape to the host. The proxy's value is that it
removes the raw socket from the application containers, constrains the API surface,
and provides one auditable choke point.

A genuinely isolated deployment needs one of:

- a **dedicated, disposable sandbox host** whose compromise costs nothing, with
  `DOCKER_HOST` pointing at it over mTLS
- **rootless Docker** or **Podman** for the sandbox daemon
- **VM-level isolation** — gVisor (`runsc`), Kata Containers, or Firecracker

Note that `SANDBOX_RUNTIME` exists in the configuration with a `runsc` option, but
`DockerSandboxAdapter` never reads it — gVisor is **not** currently wired up.

### Sandbox container hardening (already implemented)

`SandboxSecurityPolicy.get_container_security_options` applies: `read_only=True`,
`cap_drop=["ALL"]`, `no-new-privileges`, `network_mode="none"`, CPU/memory/PID
caps, `tmpfs` for `/tmp` and `/run` with `noexec,nosuid`, and log size caps.
Environment is allowlisted, dropping anything matching
`SECRET|KEY|TOKEN|PASSWORD|AUTH|CREDENTIAL|AWS_|DATABASE_|POSTGRES_|REDIS_|…`.

### Workspace path identity

`create_sandbox` builds its scratch directory from `tempfile.gettempdir()` **inside
the backend/worker container**, then hands that path to the Docker daemon as a bind
mount *source*. The daemon resolves it on the **host**. So the same absolute path
must mean the same directory in both places, which is why `compose.prod.yml` mounts:

```yaml
- ${SANDBOX_WORKSPACE_ROOT}:${SANDBOX_WORKSPACE_ROOT}   # identical both sides
```

and sets `TMPDIR` to the same value.

Prepare the host directory before the first deploy:

```bash
sudo mkdir -p /srv/agent/sandboxes
sudo chown 10001:10001 /srv/agent/sandboxes
```

**Known limitation:** on Docker Desktop (macOS/Windows) the container path and the
host path cannot be made identical, because the daemon runs in a VM. The dev stack
therefore uses a named volume and accepts the divergence: files written through
`write_file` are not visible inside the sandbox container. Sandbox file round-trips
are only faithful on a Linux host. Nothing currently copies a workspace in
(`create_sandbox` is always called with `workspace_path=""`), so this affects
write-then-execute flows rather than everyday use.

### Orphaned sandboxes

Sandbox containers are created through the Docker API, so Compose does not know
about them and `docker compose down` will not remove them. Two mechanisms handle
this:

1. **Shutdown hook** — the API lifespan calls `destroy_all_sandboxes()`, and the
   Celery worker does the same on child shutdown.
2. **Reaper** — `app.worker.tasks.reap_orphaned_sandboxes` runs on a beat schedule
   (`SANDBOX_REAPER_INTERVAL_SECONDS`, default 900s) and removes `sb_*` containers
   and workspace directories older than `SANDBOX_ORPHAN_TTL_SECONDS` (default
   3600s). This catches SIGKILL, OOM kills and host reboots, which no in-process
   hook can.

Pre-pull the runtime images on the host so the first session does not pay for it
inside a request:

```bash
docker pull python:3.11-slim   # default; also node:20-alpine, golang:1.22-alpine, rust:1.75-slim
```

---

## 7. Scaling constraints

**The API is pinned to one replica and one uvicorn worker. This is a correctness
constraint, not a capacity decision.**

Three pieces of state live in plain process memory:

| State | Location |
| --- | --- |
| Agent sessions | `SESSIONS_DB` / `STATE_MACHINES_DB` dicts in `app/api/v1/endpoints/sessions.py` |
| Rate limiter | `OrderedDict` in `app/core/rate_limiter.py` |
| Brute-force lockout | `OrderedDict` in `app/services/brute_force_service.py` |

With two replicas or two workers:

- a session created on replica A returns **404 from replica B**, because
  `_load_session_for_caller` cannot distinguish "unknown id" from "not yours"
- rate limits multiply by the replica count
- lockout counters reset when a request lands elsewhere

Scaling out requires moving that state to Redis or PostgreSQL first. Until then:

| Service | Scalable | Why |
| --- | --- | --- |
| `backend` | **No — pinned to 1** | in-process session state |
| `worker` | Yes | pulls independent tasks from Redis |
| `beat` | **No — must be 1** | multiple schedulers fire the reaper N times |
| `frontend` | Yes | stateless static files |
| `reverse-proxy` | Yes | stateless (rate-limit zones are per-instance) |

Worker capacity: host load is roughly
`WORKER_REPLICAS × CELERY_CONCURRENCY × SANDBOX_MAX_CPUS`, because every concurrent
task holds its own sandbox container. With the defaults (1 × 2 × 2.0) that is up to
4 CPUs of sandbox load on top of the worker itself.

### Related known gap

Agent runs still execute **in the API process** via FastAPI `BackgroundTasks`. The
worker service, its queue and `run_agent_session` are all in place and running, but
nothing enqueues agent runs yet, because moving execution out of the API process
requires the same shared session store described above — `GET /sessions/{id}` has to
be able to read status written by a different process. Until that lands the worker's
live job is sandbox garbage collection. A rolling restart therefore **kills
in-flight agent runs**; the shutdown hook logs how many were lost.

---

## 8. Migrations

`migrate` is a one-shot service running `alembic upgrade head` from the same image
that will serve traffic, so the schema is applied by exactly the build being
deployed.

```yaml
depends_on:
  migrate:
    condition: service_completed_successfully
```

A failed migration exits non-zero, the condition is never satisfied, and the API
never starts against a schema it does not expect.

**Only the `migrate` service may apply migrations.** `ALEMBIC_UPGRADE_ON_START` is
`0` everywhere else; setting it on the API would mean every replica racing
`upgrade head` on the same database.

CI verifies four properties on every pull request (`.github/workflows/pr.yml`,
stage 9): exactly one head, a clean upgrade from empty, **no model/migration
drift** (autogenerate must produce an empty migration), a working
`downgrade base` → `upgrade head` cycle, and idempotency when already at head.

### Destructive migrations

The ordering above is safe for **additive** changes only, because old code briefly
runs against the new schema. Dropping or renaming a column requires expand/contract
across three releases:

1. **Expand** — add the new column, write to both, read from the old
2. **Migrate** — backfill; switch reads to the new column
3. **Contract** — stop writing the old column; drop it

Do not ship a destructive migration through the normal release path.

---

## 9. Backup strategy

`pg-backup` runs `deploy/scripts/pg_backup.sh --loop`, producing a
custom-format (`-Fc`) dump every `BACKUP_SCHEDULE_SECONDS` (default 24h) and
pruning past `BACKUP_RETENTION_DAYS` (default 14).

Properties that matter:

- **Atomic** — written as `.dump.partial` and renamed only on success, so a crashed
  backup can never be mistaken for a restorable one.
- **Verified** — every dump is checked with `pg_restore --list` before being
  accepted. This is the difference between having backups and having files.
- **Checksummed** — a `.sha256` companion, verified by the restore script.
- **Non-root** — runs as `postgres`, which is why `postgres-init` chowns
  `/backups` first.

### RPO / RTO

| Method | RPO (data loss) | RTO (time to restore) |
| --- | --- | --- |
| Logical dumps only | **up to 24h** (the backup interval) | minutes — `pg_restore -j 4` |
| Dumps + WAL archive | **≈ 5 minutes** (`archive_timeout=300`) | longer — restore base, then replay WAL |

`compose.prod.yml` enables `wal_level=replica`, `archive_mode=on` and an
`archive_command` copying completed segments to the `agent-postgres-wal-archive`
volume. That is what makes section 10 possible.

### Two things this does not yet do

**Backups live on the same host as the database.** One disk or host loss takes
both. That is not disaster recovery. Set `BACKUP_S3_URI` (and provide the `aws`
CLI in the image) or otherwise copy off-host. Same for the WAL archive: replace the
local `cp` with `wal-g` or `pgBackRest` shipping to object storage.

**An unrehearsed backup is a hypothesis.** Rehearse quarterly into a scratch
database — the script supports it directly:

```bash
docker compose -f compose.prod.yml --env-file ../.env exec postgres \
  createdb -U "$POSTGRES_USER" restore_rehearsal
docker compose -f compose.prod.yml --env-file ../.env run --rm pg-backup \
  /bin/sh /scripts/pg_restore.sh --latest --target-db restore_rehearsal --yes
```

---

## 10. Database recovery strategy

### A. Restore the latest logical backup

Loses everything written since that dump.

```bash
cd /opt/agent-platform/deploy
COMPOSE="docker compose -f compose.prod.yml --env-file ../.env --env-file ../deployment-manifest.env"

# 1. Stop everything that writes. Do not skip this: restoring underneath a
#    running application produces a database that matches neither.
$COMPOSE stop backend worker beat

# 2. Inspect what is available
$COMPOSE run --rm pg-backup /bin/sh /scripts/pg_restore.sh --list

# 3. Restore (verifies the checksum, then the archive, then asserts the result)
$COMPOSE run --rm pg-backup /bin/sh /scripts/pg_restore.sh --latest

# 4. Bring the schema up to what the deployed code expects
$COMPOSE run --rm migrate alembic upgrade head

# 5. Restart and verify
$COMPOSE up -d backend worker beat
bash scripts/health_check.sh "$PRODUCTION_URL"
```

`pg_restore.sh` refuses to report success on an empty restore: it asserts the
public schema has tables and reports the `alembic_version` it found.

### B. Point-in-time recovery

For "restore to 14:32, just before the bad migration". Uses the base backup plus
the WAL archive.

```bash
# 1. Stop PostgreSQL and preserve the damaged data directory — do not delete it,
#    it is evidence and may be the only copy of recent writes.
$COMPOSE stop postgres backend worker beat
docker run --rm -v agent-postgres-data:/data -v /srv/agent/forensics:/out \
  alpine tar czf /out/pgdata-damaged-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C /data .

# 2. Restore the base backup into an empty data directory, then create
#    recovery.signal and set the recovery target:
#      restore_command = 'cp /wal-archive/%f %p'
#      recovery_target_time = '2026-08-25 14:32:00+00'
#      recovery_target_action = 'promote'
#
# 3. Start PostgreSQL. It replays WAL to the target and promotes.
# 4. Verify data at the target time BEFORE restarting the application.
# 5. Only then: $COMPOSE up -d
```

PITR is the reason `archive_mode` is on. Rehearse it at least once; the first time
should not be during an incident.

### C. Rolling back a bad migration

Container rollback cannot undo a schema change — reverting code does not un-drop a
column. This is why the release pipeline takes a **verified backup before
migrating**, and why the automatic rollback job deliberately rolls back *code
only*. Choose consciously:

- Migration was additive and the new code is bad → roll back code, leave schema.
- Migration was destructive and lost data → restore the pre-migration backup (A),
  or PITR to just before it (B). A human decision, never automatic.
- Migration has a tested `downgrade` and no data was lost →
  `run --rm migrate alembic downgrade -1`.

---

## 11. Graceful shutdown

| Layer | Mechanism |
| --- | --- |
| PID 1 | `entrypoint.sh` ends in `exec "$@"`, so the app is PID 1 and receives SIGTERM directly. Without `exec`, the shell would swallow it and Docker would SIGKILL after the grace period. |
| Zombie reaping | `init: true` on backend and worker. |
| API | `--timeout-graceful-shutdown 30`; the lifespan hook then destroys sandboxes, disposes the DB pool, and warns about in-flight runs. |
| Worker | Celery warm shutdown on SIGTERM finishes the running task; `stop_grace_period: 300s` because an agent run is long. |
| nginx | `stop_signal: SIGQUIT` — graceful. Plain SIGTERM is a *fast* shutdown that drops in-flight requests. |
| PostgreSQL | 60s grace so a shutdown checkpoint can finish; killing mid-checkpoint forces crash recovery on the next start. |
| Redis | 30s grace for a final AOF fsync. |

`stop_grace_period` always exceeds the application's own timeout, or the app would
be killed mid-cleanup. Verified in CI: the image-build stage sends SIGTERM and
asserts `Application shutdown complete` appears in the logs.

---

## 12. Log management

Every service uses the `json-file` driver with `max-size`, `max-file` and
`compress`, bounding worst-case disk at roughly
`max-size × max-file × containers`. An unbounded log on a crash-looping container
will fill a disk and take the host down.

Both sides emit structured JSON: the backend via structlog, the proxy via a
`log_format json_combined` with `escape=json` (which stops a crafted header from
injecting a fake log record). `correlation_id` and `request_id` are propagated by
`proxy-common.conf`, so a request can be traced across proxy → API → worker.

For production, forward to a collector (Loki, CloudWatch, Elastic) rather than
relying on local files — local logs die with the host, and `docker logs` is not a
retention strategy. uvicorn's own access log is disabled (`--no-access-log`)
because `ObservabilityMiddleware` already emits one structured record per request.

---

## 13. Operational runbook

### First deployment

```bash
# On the host
sudo mkdir -p /opt/agent-platform /srv/agent/sandboxes
sudo chown 10001:10001 /srv/agent/sandboxes
cd /opt/agent-platform

# Configuration
cp .env.example .env && chmod 600 .env   # fill in every CHANGE-ME
# Image digests, from the GitHub release artifact
cp deployment-manifest.env .

# TLS certificates
sudo cp fullchain.pem privkey.pem deploy/reverse-proxy/certs/
sudo chown 101:101 deploy/reverse-proxy/certs/*.pem
sudo chmod 600 deploy/reverse-proxy/certs/privkey.pem

docker pull python:3.11-slim

cd deploy
docker compose -f compose.prod.yml --env-file ../.env --env-file ../deployment-manifest.env \
  up -d --wait --wait-timeout 300

bash scripts/health_check.sh https://agent.example.com
```

### Routine deploy

Push a semver tag. The release pipeline runs every mandatory check, builds
digest-pinned images, backs up the database, migrates, deploys, verifies health,
and rolls back automatically if verification fails. See `docs/CICD.md`.

### Manual rollback

```bash
cd /opt/agent-platform
# Set the previous digests in deployment-manifest.env, then:
cd deploy
docker compose -f compose.prod.yml --env-file ../.env --env-file ../deployment-manifest.env \
  up -d --wait --wait-timeout 240
bash scripts/health_check.sh https://agent.example.com
```

### Diagnostics

```bash
$COMPOSE ps                                   # state and health
$COMPOSE logs -f --tail=100 backend
docker inspect --format '{{.State.Health.Status}}' <container>
$COMPOSE run --rm migrate alembic current     # schema revision
$COMPOSE exec worker celery -A app.worker.celery_app:celery_app inspect ping
docker ps --filter "name=^sb_"                # live sandbox containers
$COMPOSE exec redis redis-cli info persistence
```

### TLS renewal

Certificates are mounted, not baked, so renewal does not require a rebuild. After
renewing into `deploy/reverse-proxy/certs/`:

```bash
$COMPOSE exec reverse-proxy nginx -s reload
```

The ACME HTTP-01 webroot is the `agent-certbot-webroot` volume, served at
`/.well-known/acme-challenge/` on port 8080 before the HTTPS redirect.

---

## 14. Porting to a real orchestrator

The container contract was built to survive this move. What changes:

| Compose concept | Kubernetes equivalent |
| --- | --- |
| `migrate` + `service_completed_successfully` | `Job` + `initContainer`, or a Helm `pre-upgrade` hook |
| `HEALTHCHECK` | `livenessProbe` → `/api/v1/health`, `readinessProbe` → `/api/v1/readiness` |
| `deploy.resources` | `resources.requests` / `resources.limits` |
| `stop_grace_period` | `terminationGracePeriodSeconds` |
| `env_file` | `ConfigMap` + `Secret` |
| Named volumes | `PersistentVolumeClaim` |
| `internal: true` networks | `NetworkPolicy` |
| `sandbox-broker` | a dedicated node pool with a taint, or a separate sandbox cluster |
| `pg-backup` | `CronJob` |
| `read_only` / `cap_drop` / `no-new-privileges` | `securityContext` + Pod Security Standards |

Two caveats carry over unchanged: the API still cannot exceed one replica until
session state moves out of process memory, and the readiness probe must parse the
response **body**, because `/api/v1/readiness` returns HTTP 200 even when
unhealthy.

---

## 15. Residual risks

| Risk | Severity | Mitigation / status |
| --- | --- | --- |
| Sandbox broker permits container creation with bind mounts | **High** | Narrowed by allowlist; real fix is a dedicated sandbox host or VM isolation (section 6). |
| Redis has no authentication | Medium | Network isolation only. `Settings` has no `REDIS_PASSWORD` field and `REDIS_URL` cannot carry one, so enabling `requirepass` would break the app. Needs a config change first. |
| Single host | Medium | Accepted for this topology. Section 1. |
| Secrets in a file on disk | Medium | Mode 0600, gitignored, never in an image. A secret store is the upgrade. |
| API limited to one replica | Medium | Documented in section 7; needs shared session state. |
| Unpinned Python dependencies | Medium | Section 5 — compile a hash-pinned lock file. |
| Backups co-located with the database | Medium | Set `BACKUP_S3_URI`. |
| Agent runs die on deploy | Low–Medium | Inherent while runs execute in the API process; the shutdown hook logs the loss. |
| `/api/v1/metrics` unauthenticated | Low | Blocked at the proxy to private CIDRs; the application still has no auth on it. |
| API docs served unconditionally | Low | Blocked at the proxy in the TLS template. |
| gVisor not wired up | Low | `SANDBOX_RUNTIME=runsc` is accepted but never read by the adapter. |
