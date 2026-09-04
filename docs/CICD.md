# CI/CD Pipeline

Two workflows:

- `.github/workflows/pr.yml` — 11 stages on every pull request and on pushes to
  long-lived branches. Also **callable**, which is what the release uses as its gate.
- `.github/workflows/release.yml` — build, tag, push, migrate, deploy, verify, and
  roll back automatically on failure.

---

## Prerequisite: this workspace is not a git repository yet

`git rev-parse` fails here, so no workflow can run until the project is initialised
and pushed:

```bash
git init
git add .
git commit -m "Add deployment architecture and CI/CD pipeline"
git branch -M main
git remote add origin git@github.com:<org>/<repo>.git
git push -u origin main
```

Check `.gitignore` is in place first — it is, and it excludes `.env`, keys, certs,
`.venv/`, `node_modules/` and `dist/`.

---

## Pull request pipeline

| # | Stage | Job | Mandatory | What it proves |
| --- | --- | --- | --- | --- |
| 1 | Install dependencies | `dependencies` | yes | Dependencies resolve; the app imports; the Celery app loads and registers both tasks |
| 2 | Formatting | `format` | yes | Every **changed** file is formatted (`ruff format`, `prettier`) |
| 3 | Linting | `lint` | yes | `ruff check` repo-wide, `eslint` repo-wide |
| 4 | Type checking | `types` | yes | `mypy` (with a documented debt baseline), `tsc --noEmit` |
| 5 | Unit tests | `unit-tests` | yes | 392 tests + coverage |
| 6 | Integration tests | `integration-tests` | yes | Against **real** PostgreSQL 15 and Redis 7 service containers |
| 7 | Security | `security` | yes | gitleaks, no committed `.env`, no secrets in Dockerfiles, pip-audit, npm audit, bandit, Trivy image scan, non-root assertion |
| 8 | Build images | `build-images` | yes | All 4 images build; the API image starts, answers `/health`, and shuts down gracefully |
| 9 | Verify migrations | `migrations` | yes | Single head; empty→head; **no model drift**; downgrade→upgrade; idempotent |
| 10 | Frontend tests | `frontend-tests` | yes | 22 vitest tests + coverage + production build + output assertions |
| 11 | End-to-end | `e2e` | yes | Full stack from production images, verified over HTTP through the reverse proxy |
| — | Quality debt | `quality-debt` | **no** | Measures excluded debt so it stays visible |
| — | **All required checks** | `required-checks` | yes | **The single status check to require in branch protection** |

Stages 1–10 run in parallel. Only `e2e` waits (on `build-images`).

### Branch protection

Require **exactly one** check: `All required checks`.

Do not mark the individual jobs required. A **skipped** job reports success to
GitHub's API, so a path filter, a cancellation or an early exit could let a broken
change merge. `required-checks` runs with `if: always()` and inspects
`needs.<job>.result` explicitly, failing unless every mandatory job is literally
`success`.

Recommended alongside it: require a pull request before merging, require branches to
be up to date, and dismiss stale approvals on new commits.

---

## Never deploying code that fails mandatory checks

This is structural, not procedural. `release.yml` calls the entire pull-request
pipeline as a reusable workflow against the exact commit being released:

```yaml
verify:
  needs: [version]
  uses: ./.github/workflows/pr.yml
```

and every subsequent job depends on it, directly or transitively:

```
version → verify → build-push → release-tag → backup → migrate → deploy → health-check
                                                                              │
                                                                       rollback (on failure)
```

Consequences:

- A failing lint, type error, test, migration check or security finding means
  `verify` fails, so **`build-push` never runs** — there is no artifact to deploy.
- Reusing `pr.yml` rather than restating its stages means the merge gate and the
  release gate cannot drift apart.
- `concurrency: production-release` with `cancel-in-progress: false` prevents two
  deploys overlapping and never interrupts a migration in flight.
- The `production` environment gates `backup`, `migrate`, `deploy` and `rollback`
  behind whatever approval you configure on it.

---

## Release pipeline

Trigger by pushing a semver tag, or `workflow_dispatch` with a version (and an
optional `dry_run` that builds and pushes but does not migrate or deploy).

| # | Job | What it does |
| --- | --- | --- |
| 0 | `version` | Validates strict semver (`vMAJOR.MINOR.PATCH`), computes the image prefix |
| 1 | `verify` | Re-runs all 11 mandatory stages on this commit |
| 2 | `build-push` | **Refuses to overwrite an existing version tag**; builds and pushes with SBOM + provenance attestation; records the **digest** |
| 3 | `release-tag` | Collects digests into `deployment-manifest.env`; creates the git tag and GitHub release |
| 4 | `backup` | Verified pre-migration backup; records current digests as the rollback target |
| 5 | `migrate` | `alembic upgrade head` from the exact API image being released |
| 6 | `deploy` | Syncs config, pulls **by digest**, `up -d --wait` |
| 7 | `health-check` | Runs `deploy/scripts/health_check.sh` against the public URL |
| 8 | `rollback` | Automatic, on deploy or health-check failure |

### Immutability

Three mechanisms:

1. `docker manifest inspect` runs **before** building and fails if the version tag
   already exists in the registry. Re-releasing a version would silently change what
   a previously recorded digest means.
2. Deployments reference `image@sha256:…`, never a tag. `compose.prod.yml` declares
   the image variables as `${VAR:?message}`, so a missing digest fails fast instead
   of resolving a mutable `latest`.
3. Every image carries a build-provenance attestation and an SBOM.

### Automatic abort and rollback

`docker compose up -d --wait` exits non-zero unless every service with a health
check reports healthy, so a failed rollout fails the job rather than appearing to
succeed. `health-check` then verifies real behaviour from outside.

If either fails, `rollback` fires:

1. Captures per-service logs **first** — replacing containers destroys the only
   evidence of why the release failed.
2. Restores the previous digests and waits for health.
3. Re-runs `health_check.sh` to confirm service is actually back.
4. **Exits non-zero anyway**, so a successful rollback is never mistaken for a
   successful release.

**Rollback is code-only, deliberately.** It does not run `alembic downgrade`.
Automatically reversing a schema change on a production database because a health
check failed risks destroying data the new schema already accepted. The
pre-migration backup is the recovery path, and using it is a human decision —
procedure in `docs/DEPLOYMENT.md` §10.

If the first-ever deploy fails there is nothing to roll back to; the job says so and
leaves the stack up for inspection rather than tearing it down.

### Required secrets

| Secret | Used by |
| --- | --- |
| `DEPLOY_SSH_KEY` | backup, migrate, deploy, rollback |
| `DEPLOY_HOST` | as above |
| `DEPLOY_USER` | as above (must be in the `docker` group) |
| `PRODUCTION_URL` | health-check, rollback |
| `GITHUB_TOKEN` | provided automatically; needs `packages: write` for GHCR |

Production configuration (`SECRET_KEY`, `POSTGRES_PASSWORD`, provider keys) lives in
`/opt/agent-platform/.env` **on the host** and never passes through CI.

---

## Adoption decisions, and why

These tools were added to a codebase that had never been linted, formatted or type
checked. A gate that is red on arrival blocks every pull request and gets bypassed,
so each one was calibrated against a real run.

### Formatting is changed-files-only

`ruff format --check` reports **106 of 138** backend files as unformatted, and
prettier **36** frontend files. A repo-wide gate would fail every pull request until
someone lands a ~140-file mechanical reformat — a change that belongs in its own
commit, not forced through an unrelated review.

So: files a pull request touches must be formatted; legacy files are normalised as
they are next edited. To switch to repo-wide enforcement:

```bash
cd backend && ruff format app alembic tests
cd ../frontend && npm run format
# commit that alone, then replace the changed-file logic in stage 2 with `--check .`
```

### Linting enforces bugs, not style

`backend/pyproject.toml` selects `E4`, `E7`, `E9`, `F63`, `F7`, `F82`, `F811`,
`PLE`, `B`, `T20` — rules that catch defects. **Verified clean repo-wide.**

Ignored with reasons: `B008` (FastAPI's `Depends()` in a default argument is the
core idiom, 42 occurrences, all correct), `B017`, `B904`. Per-file: `F821` in
`app/infrastructure/db/models/` (SQLAlchemy string forward references resolved by
the declarative registry, invisible to static analysis) and `E402` in three files
with deliberate late imports.

The wider modernisation set (`I`, `F401`, `UP`, `SIM`, `RUF`, `ASYNC`, `BLE`) runs
in the **advisory** job. Current debt: `UP006` 368, `UP045` 346, `UP035` 151,
`F401` 148, `I001` 120, `BLE001` 68, `ASYNC230` 6.

**`ASYNC230` is the one worth prioritising** — blocking `open()` inside async
functions in the sandbox adapter stalls the event loop for every concurrent request.

### mypy has a per-module debt baseline

Not `--strict`: that reports thousands of errors here. `check_untyped_defs = false`
means annotating a function is what opts it in, so the ratchet is automatic.

Ten modules are listed with `ignore_errors = true`, totalling 24 errors, each
annotated with its cause. **Enforced (not excluded):** `app.main`, `app.worker.*`,
`app.core.*`, `app.api.*`, `app.services.*`, `app.domain.*`. Remove an entry, run
mypy, fix what it reports.

Two config settings were needed to make mypy run at all:
`explicit_package_bases` + `namespace_packages` (several package directories have no
`__init__.py`, so `app/domain/entities/git.py` and `app/api/v1/endpoints/git.py`
both mapped to module `git` and mypy aborted), and `follow_imports = "skip"` for
untyped vendor SDKs.

### Accepted security findings

`backend/.pip-audit-ignore` holds accepted advisories, each with a justification and
a remediation plan. Currently one:

**PYSEC-2026-1325 — `ecdsa` 0.19.2.** Reached via
`python-jose[cryptography] → ecdsa`. **No fix version exists**, so failing on it
would block every pull request forever. The advisory concerns side-channel
resistance in ECDSA signing; this application signs JWTs with **HS256** (HMAC), so
the vulnerable path is not reachable. It *would* become reachable if
`settings.ALGORITHM` changed to `ES256`/`ES384`/`ES512`.
**Recommended remediation: replace `python-jose` with `PyJWT`**, which uses
`cryptography` directly and drops `ecdsa` and `rsa` entirely.

Bandit's two `B108` hits in `app/infrastructure/sandbox/policy.py` are annotated
with `# nosec B108` and a reason at the call site: they are paths *inside the
sandbox container* (a `noexec,nosuid` tmpfs), not predictable temp files on the host.

Trivy runs with `--ignore-unfixed`. Blocking on a base-image CVE with no available
patch leaves no action to take, and a permanently red gate gets bypassed.

`npm audit` runs at `--audit-level=high`; the moderate tier here is dominated by
build-time-only packages that cannot affect the shipped bundle.

---

## Test strategy

Marker-based selection (`backend/pytest.ini`). Mandatory gate:

```bash
pytest -m "not docker and not postgres and not vuln and not quarantine"
# 392 passed, 1 skipped
```

| Marker | Excluded from mandatory gate because | Covered by |
| --- | --- | --- |
| `docker` | needs a reachable Docker daemon | stage 11 (E2E) |
| `postgres` | needs a real PostgreSQL server | stage 6 (integration) |
| `vuln` | **asserts behaviour deliberately not implemented yet** — documents open findings, expected to fail | advisory job |
| `quarantine` | encodes pre-hardening behaviour — see below | advisory job |

### The determinism fix

The suite was **order-dependent** before this work. `conftest.py`'s only reset
fixture was `@pytest_asyncio.fixture(autouse=True)`, and with `asyncio_mode =
strict` pytest-asyncio does not apply async fixtures to **sync** tests. Every sync
test (most of the auth and API suite) therefore never reset the process-global
brute-force and rate-limiter counters, and depended on some earlier async test
having created the tables.

Symptom: `pytest tests/auth/test_authentication.py::TestAbuseControls` failed with
5 errors on its own while passing as part of a full run. In CI, sharding or
reordering would have produced random failures.

Fixed with a `_bootstrap_schema()` call at import (a throwaway engine, disposed, so
`test_engine`'s `StaticPool` connection is not bound to a dead event loop) and a
plain **sync** `_reset_abuse_controls` autouse fixture. Results are now identical
whether you run one class, one file, or the whole suite.

### Quarantined tests — 29, all pre-existing

These fail against the current application and are **not** flaky. They encode the
API as it behaved before it was secured. None were caused by this work: the totals
were 29 failures before and after.

| Location | Count | Cause | Fix |
| --- | --- | --- | --- |
| `tests/e2e/test_agent_session_flows.py` | 18 | Session endpoints now require `Depends(get_current_user)` and a `project_id` with a membership check; unauthenticated requests get 401 where 422/200 is asserted | Add an authenticated client fixture and a real project id |
| `tests/test_git_integration.py` | 6 | `LocalGitProvider` now refuses to run without a sandbox (finding CMD-01 removed host execution) | Construct it with the fake sandbox from `tests/support/sandboxes.py` |
| `tests/test_auth_security.py` | 3 | Lockout now returns **423**, not 401 (finding AUTH-03); reset/verification tokens are no longer echoed in responses | Update expected statuses; wire an SMTP sender |
| `tests/auth/test_authentication.py::TestAbuseControls` | 2 | Same 423-vs-401 change | Expect 401 up to the threshold, 423 after |

Worth noting: `TestAbuseControls` also contains a **`vuln`-marked test asserting
423 that now passes**. The codebase holds both expectations at once — the security
fix landed, and the older assertions were never updated.

### Frontend tests

22 vitest tests across the three stateful stores, in `jsdom` (required:
`useAuthStore.ts` reads `localStorage` at module scope, so `node` throws on import).
`passWithNoTests: false`, so deleting the suite fails the build.

One of these found a real bug: `startNewTask` derived ids from `Date.now()` alone,
so a retry within the same millisecond produced a **colliding run id** and
overwrote the previous run's record in `DEFAULT_EXECUTIONS`. Fixed with a monotonic
counter (`run-<epoch>-<sequence>`) rather than by weakening the assertion.

---

## Bugs found and fixed while building this

Calibrating the gates surfaced genuine defects:

| Issue | Impact |
| --- | --- |
| `alembic/env.py` fed the **sync** `postgresql://` URL into an **async** engine, and `psycopg2` is not a dependency | `alembic upgrade head` could never run. Automated migrations were impossible. |
| No `alembic/versions/` and no `script.py.mako` | **No migrations existed at all.** A fresh database had zero schema, while `/readiness` still passed because `SELECT 1` works. |
| `app/core/prompts/manager.py` used `List[...]` without importing `List` | Latent `NameError`; survives only because PEP 526 does not evaluate attribute annotations. |
| API shutdown only logged | Sandbox containers and temp directories leaked on every restart; the DB pool was never disposed. |
| Order-dependent test suite | Random CI failures under sharding. |
| Frontend run-id collision | Overwritten agent run records. |
| `postgres` `archive_command` target volume is root-owned | WAL archiving would fail permission-denied, `pg_wal` would grow until the disk filled — silent until it became an outage. Fixed with `postgres-init`. |
| 4 × ambiguous `l` variable, 1 unused loop variable, 25 unused frontend imports | Dead code and readability. |
| `tests/e2e/test_agent_session_flows.py` had mixed line endings | Crashed ruff 0.16.4's diff renderer outright. |

One issue found but **not** fixed, as it is outside deployment scope:
`SessionWorkspace.tsx` posts to `/api/v1/sessions` **without `project_id`**, which
the API now requires — that request returns 422. The frontend also sends no
`Authorization` header, so it would get 401 first. The UI cannot currently start a
session.

---

## Local reproduction

Run what CI runs, before pushing:

```bash
# Backend
cd backend
pip install -r requirements-dev.txt
ruff format --check app alembic tests    # or `ruff format` to fix
ruff check app alembic tests
mypy
pytest -m "not docker and not postgres and not vuln and not quarantine"
pip-audit --requirement requirements.txt $(sed '/^#/d;/^$/d;s/^/--ignore-vuln /' .pip-audit-ignore)
bandit -r app -ll

# Frontend
cd ../frontend
npm ci
npm run format:check                     # or `npm run format`
npm run lint
npm run typecheck
npm run test:coverage
npm run build

# Full stack, exactly as stage 11 does it (needs Docker)
bash deploy/scripts/smoke_test.sh
KEEP_UP=1 bash deploy/scripts/smoke_test.sh   # leave it running to poke at
```

---

## Pinned tool versions

| Tool | Version | Why pinned |
| --- | --- | --- |
| ruff | `==0.16.4` | A minor bump can add rules to an existing selector and turn a green gate red with no code change. |
| mypy | `==2.3.1` | Same reasoning. |
| Python | 3.11 | Matches `FROM python:3.11-slim`. |
| Node | 20 | Matches `FROM node:20-alpine`. |

`pip-audit` and `bandit` are floored, not pinned: their value is knowing about *new*
advisories, so they should move.
