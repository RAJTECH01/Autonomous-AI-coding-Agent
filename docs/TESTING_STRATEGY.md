# Production Testing Strategy — Autonomous Coding Agent Platform

**Suite:** `backend/tests/` — 565 tests (476 new + 89 pre-existing)
**Status:** `422 passed, 9 skipped, 134 xfailed` in ~3 minutes, no Docker daemon, no network, no model API keys
**Config:** `backend/pytest.ini`

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests -q
```

---

## 1. Principle: fake only at the boundaries you must not cross

"Do not mock everything" is the design constraint, so the suite substitutes exactly
three things and runs everything else for real:

| Substituted | Why | Replacement |
|---|---|---|
| Model provider | Paid, rate-limited, non-deterministic | `ScriptedAIProvider` / `FailingAIProvider` / `RateLimitedAIProvider` / `SlowAIProvider` (`tests/support/ai_providers.py`) |
| Docker daemon | Absent on most CI workers | `InProcessSandbox` — real temp directory, real file I/O, real subprocesses, **production containment policy** (`tests/support/sandboxes.py`) |
| Postgres | Needs a server | Real SQLAlchemy engine on file-backed SQLite, real schema, real constraints |

Everything below is exercised for real: the FastAPI app and its middleware, the
dependency graph, Pydantic validation, Argon2 hashing, JWT signing, the database
schema and its constraints, the repositories, the `ControlledToolLayer`, every
tool implementation, `PathValidator`, `SandboxSecurityPolicy`, the prompt manager
with the real template files on disk, the analyzer/planner/tester/reviewer
sub-agents, the `AgentStateMachine`, `LocalGitProvider` **against the real `git`
binary**, and `pytest` itself running real broken code inside the sandbox.

Two consequences worth knowing:

- **Shell-injection assertions are real.** `tests/support/shell.py` re-parses the
  command string the tool layer produced using `shlex` with
  `punctuation_chars=True`, i.e. POSIX shell operator rules. If a payload becomes
  its own command segment, quoting was broken. This behaves identically on Linux
  and Windows, where `sh` does not exist.
- **"Generated syntax error", "runtime error" and "failing tests" are genuine.**
  The sandbox runs `sys.executable -m pytest` against hostile project trees, so
  the classification logic is tested against real interpreter output, not canned
  strings.

---

## 2. The twelve categories

| # | Category | Location | Tests | What it establishes |
|---|---|---|---|---|
| 1 | Unit | `tests/unit/` | 68 | Pure decision logic: path policy, output truncation, env sanitisation, approval policy, JWT/password primitives, rate-limit windows, protected-branch detection, cost arithmetic |
| 2 | Integration | `tests/integration/` | 17 | Real components wired together: prompt templates from disk, analyzer→planner handover, provider factory, **real git** branch/commit/diff/push refusal, git tools through the tool layer |
| 3 | API | `tests/api/` | 26 | HTTP contract: health/readiness/metrics, error envelope, correlation headers, CORS, project CRUD, pagination, validation, database-failure response |
| 4 | Database | `tests/database/` | 20 | Real constraints: unique email/slug/token, membership uniqueness, NOT NULL, soft-delete filtering, cascades, transaction rollback, pagination correctness, agent-run persistence, parameterisation |
| 5 | Agent state machine | `tests/agent/` | 31 | Stage progression, step history, approval gate, approve/reject/cancel/modify, limit enforcement, tool-call plumbing, memory boundaries |
| 6 | Tools | `tests/tools/` | 28 | Registry completeness, schema validity, permission classes, file-tool behaviour on a real filesystem, budgets, timeouts, audit records, secret masking |
| 7 | Sandbox | `tests/sandbox/` | 27 | Containment, real code execution, output truncation, lifecycle and cleanup, adapter fail-closed behaviour, plus a **real-container** suite behind `-m docker` |
| 8 | Authentication | `tests/auth/test_authentication.py` | 34 | Registration, login, token validation, expiry, forged signatures, rotation and replay, logout, lockout, throttling |
| 9 | Authorization | `tests/auth/test_authorization.py` | 28 | Anonymous rejection, tenant isolation, route-level identity requirements, tool RBAC, approval-gate ownership |
| 10 | Failure / retry | `tests/failure/` | 18 | Real failing/broken projects, tool failure isolation, transient sandbox recovery, timeouts, repeated-failure safeguards, disk-full and vanished-workspace handling |
| 11 | End-to-end | `tests/e2e/` | 18 | HTTP request → agent run → result, including a full autonomous run that writes code, runs real pytest and completes |
| 12 | Security | `tests/security/` | 161 | Injection, traversal, sandbox escape, prompt injection, malicious repos, supply chain, secrets, SSRF/egress, resource exhaustion, deployment config |

Markers (`pytest.ini`): `unit`, `integration`, `api`, `database`, `agent`, `tools`,
`sandbox`, `authn`, `authz`, `failure`, `e2e`, `security`, `vuln`, `slow`,
`docker`, `postgres`.

---

## 3. Required scenario coverage

Every scenario from the brief, with the test that proves it. All paths are under
`backend/`.

| Scenario | Test |
|---|---|
| **Valid task** | `tests/e2e/…::TestValidTaskEndToEnd::test_autonomous_session_writes_code_runs_tests_and_completes` (writes code, real pytest passes, run COMPLETED), `…::test_plan_only_session_completes_and_returns_a_plan`, `tests/agent/…::TestValidTaskProgression::test_plan_only_run_reaches_completed_through_every_stage` |
| **Invalid requirement** | `tests/e2e/…::TestInvalidRequirements::test_missing_prompt_is_rejected_before_any_work_starts`, `…::test_out_of_range_iteration_budget_is_rejected`, `…::test_unknown_execution_mode_falls_back_to_requiring_approval`, `tests/agent/…::test_prompt_injection_in_the_requirement_does_not_grant_authority` |
| **Empty requirement** | `tests/agent/…::TestRequirementHandling::test_empty_requirement_still_produces_a_controlled_outcome`, `tests/e2e/…::test_empty_prompt_produces_a_controlled_outcome` |
| **Generated syntax error** | `tests/sandbox/…::TestRealCodeExecution::test_generated_syntax_error_is_reported_with_diagnostics`, `tests/failure/…::TestRealTestExecution::test_generated_syntax_error_is_classified` |
| **Runtime error** | `tests/sandbox/…::test_generated_runtime_error_is_reported_with_traceback`, `tests/failure/…::test_generated_runtime_error_is_classified` |
| **Failing tests** | `tests/failure/…::test_failing_tests_are_detected_and_located`, `…::test_a_project_with_no_tests_is_not_reported_as_passing` |
| **Repeated failure** | `tests/failure/…::TestRepeatedFailureSafeguards::test_an_identical_failed_patch_is_blocked_the_second_time`, `…::test_endless_rewriting_of_one_file_is_capped`, `tests/agent/…::test_iteration_limit_aborts_the_run` |
| **Timeout** | `tests/tools/…::test_slow_tool_is_timed_out_and_recorded`, `tests/failure/…::test_timeout_is_enforced_per_tool`, `tests/agent/…::test_execution_time_limit_aborts_the_run`, `tests/sandbox/…::TestRealContainerIsolation::test_timeout_terminates_the_process` (docker) |
| **Tool failure** | `tests/failure/…::TestToolFailureHandling` (5 tests), `tests/tools/…::test_sandbox_failure_is_surfaced_as_a_failed_tool_result` |
| **Sandbox failure** | `tests/sandbox/…::TestDockerAdapterFailureModes` (4 tests), `tests/e2e/…::test_sandbox_provisioning_failure_is_surfaced_as_a_request_error`, `tests/agent/…::test_dead_sandbox_does_not_crash_the_run` |
| **User cancellation** | `tests/e2e/…::test_user_cancellation_is_honoured`, `tests/agent/…::test_cancellation_is_accepted_and_terminal`, `…::test_cancellation_is_possible_from_any_state` |
| **Database failure** | `tests/api/…::TestErrorContract::test_internal_errors_do_not_leak_stack_traces` (connection dies mid-request; asserts no DSN or traceback leaks), `tests/database/…::TestTransactions` (3 tests) |
| **AI provider failure** | `tests/agent/…::test_provider_outage_fails_the_run_with_a_report`, `tests/e2e/…::test_provider_outage_is_reported_on_the_session`, `tests/integration/…::test_known_providers_either_construct_or_fail_loudly` |
| **Rate-limit response** | `tests/auth/…::TestAbuseControls::test_registration_flood_is_throttled`, `…::test_throttled_response_carries_a_correlation_id`, `tests/agent/…::test_provider_rate_limit_fails_the_run_and_is_reported_verbatim`, `tests/e2e/…::test_provider_rate_limit_is_reported_on_the_session` |
| **Malicious file path** | `tests/security/test_path_traversal_and_sandbox.py` (24 tests: traversal, prefix escape, symlink escape, `.git/hooks`, credential files, metacharacters), `tests/agent/…::test_a_malicious_tool_path_is_denied_without_killing_the_run`, `tests/tools/…::test_denied_calls_are_recorded_as_denied` |
| **Malicious command** | `tests/security/test_injection.py` (32 tests: file-tool quote breaks, git substitution, blocklist bypasses, tool injection, log injection), `tests/e2e/…::test_malicious_requirement_cannot_drive_a_destructive_action` |
| **Unauthorized project access** | `tests/auth/test_authorization.py::TestTenantIsolation` (6 tests), `tests/database/…::TestTenantScoping::test_list_user_projects_returns_only_the_callers_projects`, `tests/auth/…::TestAuthenticationIsRequired` (4 tests) |

---

## 4. The vulnerability register: strict xfail

134 tests report `XFAIL`. That is not skipping — it is an executable inventory of
open defects.

- Each asserts the **secure or correct** behaviour and carries
  `@pytest.mark.xfail(strict=True, reason="<ID>: <mechanism and impact>")` plus
  `@pytest.mark.vuln`.
- Today they fail, so they report XFAIL and the suite stays green.
- When someone fixes the defect the test passes, `strict=True` turns that XPASS
  into a **build failure**, and the fixer deletes the marker. The test becomes a
  permanent regression guard.
- A finding is closed only when its marker is gone and the test passes unmarked.

```powershell
.venv\Scripts\python.exe -m pytest tests -m vuln -q          # the open-defect register
.venv\Scripts\python.exe -m pytest tests -m "not vuln" -q    # must always be green
.venv\Scripts\python.exe -m pytest tests -m security -q
.venv\Scripts\python.exe -m pytest tests -m docker -q        # needs a daemon
```

The complement — 422 passing tests — includes deliberate **regression guards**
(named `*_regression`) that lock in controls which do work today: `network_mode=none`,
read-only rootfs, `cap_drop=ALL`, `no-new-privileges`, pid/memory caps, `..`
rejection, `search_files` query escaping, unknown-tool rejection, output
truncation, the 120 s timeout ceiling, protected-branch refusal, push
authorisation refusal, refresh-token rejection as an access token, secret masking
in audit records, and absence of f-string SQL.

---

## 5. Defects found while building this suite

Writing the tests surfaced eight problems that were not in the earlier audit. All
are now covered by a test.

| ID | Defect | Severity | Evidence |
|---|---|---|---|
| **METRICS-01** | `MetricsRegistry` self-deadlock: `get_dashboard_summary()` holds a non-reentrant `Lock` and then reads `average_execution_time`, which acquires the same lock. `GET /api/v1/metrics` and `/metrics/dashboard` hang forever, tying up a worker per request — an unauthenticated availability kill. **Fixed** (`threading.RLock`) because it also hung the entire test suite. | **High** | `tests/unit/…::test_dashboard_summary_does_not_deadlock`, `tests/api/…::test_dashboard_metrics_do_not_hang` |
| **API-01** | `PUT /api/v1/projects/{id}` always 500s. `TimestampMixin.updated_at` uses `onupdate=func.now()`, so the attribute is expired after flush; serialising the ORM object then triggers a lazy refresh outside the async context (`MissingGreenlet`). | High | `tests/api/…::test_update_returns_the_updated_project` (xfail) |
| **API-02** | `DELETE /api/v1/projects/{id}` always 500s. `ProjectService.delete_project` calls `project_repo.delete(project)`; `BaseRepository` only has `soft_delete(id)`. Projects cannot be deleted. | High | `tests/api/…::test_project_can_be_deleted` (xfail) |
| **POLICY-01** | `evaluate_plan` matches `DB_SCHEMA_KEYWORDS` only against `target_files`, never plan text, and has no force-push or database-destruction pattern. Plans saying "DROP TABLE users", "delete the production database" or "git push --force to main" pass the high-risk gate. | High | `tests/unit/…::test_destructive_sql_and_force_push_plans_should_be_flagged` (xfail) |
| **LIMIT-01** | `LimitExceededError` raised inside `execute_tool`'s `try` is swallowed by the generic `except Exception` and returned as an ordinary failed `ToolResult`. A budget breach looks like a transient tool error, so the loop retries instead of aborting. | Medium | `tests/tools/…::test_limit_breach_is_distinguishable_from_a_tool_failure` (xfail) |
| **TEST-01** | `PytestAdapter._classify_likely_cause` looks for `"AssertionError"`, but pytest renders assertion failures as `assert -1 == 5`. Every assertion failure is mislabelled "Runtime Error", and that wrong root cause is what the debugging agent receives. | Medium | `tests/failure/…::test_assertion_failures_are_classified_as_assertion_failures` (xfail) |
| **AUTH-08 / DOS-06** | Lockout and throttling both return `401 AUTHENTICATION_FAILED` / `400 DOMAIN_ERROR` with no `Retry-After`. `RateLimitExceededError` subclasses `DomainError` and falls into the generic handler, so clients cannot back off and proxies cannot shed load. | Medium | `tests/auth/…::test_lockout_uses_a_distinct_status_code`, `…::test_throttling_uses_429_with_retry_after` (xfail) |
| **AUTHZ-09** | Another tenant's project returns 403 while a non-existent id returns 404, letting an authenticated attacker enumerate project ids. | Medium | `tests/auth/…::test_nonexistent_project_is_not_distinguishable_from_a_forbidden_one` (xfail) |
| **HARNESS-01** | The suite was order-dependent and could not run as a whole. `tests/test_agent_state_machine.py` does `from tests.conftest import …`, which re-imported `conftest.py` under a second module name, creating a second engine and a second `dependency_overrides[get_db]`; the app then used a database whose schema was never created. Compounded by an in-memory SQLite whose schema lives in one connection. **Fixed** by adding `tests/__init__.py` and moving the test database to a file. | Medium | The full suite now passes in one run |

---

## 6. Recommended CI pipeline

```yaml
stages:
  fast:      pytest tests -m "unit or (api and not slow)" -q          # ~15s, every push
  standard:  pytest tests -m "not docker and not slow" -q             # ~3min, every PR - blocking
  isolation: pytest tests -m docker -q                                # needs a daemon; nightly + release
  register:  pytest tests -m vuln -q                                  # publishes the open-defect list
gates:
  - "not vuln" must be 100% green
  - no XPASS (strict xfail catches silently fixed or regressed findings)
  - coverage floor on app/core, app/infrastructure/tools, app/infrastructure/sandbox
  - pip-audit / Trivy as blocking steps (see DEP-01, INFRA-03)
```

Add `ruff` with `T20` (no `print`) to make LEAK-01 impossible to reintroduce, and
run the Docker-marked suite on a Linux runner so the symlink-escape tests
(ESC-01) execute rather than skip.

---

## 7. Honest gaps

- **9 skips, by design.** Six real-container tests skip without a Docker daemon;
  three symlink tests skip because creating symlinks needs privilege on Windows.
  On a Linux CI runner all nine execute — and the symlink tests are the ones that
  demonstrate the sandbox escape, so this matters.
- **SQLite, not Postgres.** Constraint, cascade and transaction behaviour is
  verified, but not `ON DELETE RESTRICT` enforcement details, row-level security,
  concurrent-write behaviour or migration correctness. A `postgres`-marked service
  container job should run the same `tests/database` suite.
- **Alembic migrations are untested.** No test applies migrations to an empty
  database and compares the result with `Base.metadata`.
- **No frontend tests.** `frontend/` has no test tooling configured; the log
  viewer in particular deserves an XSS test given LOG-01.
- **No load or soak testing.** Resource-exhaustion findings are proven
  structurally (unbounded stores, absent caps), not by sustained load.
- **The model is scripted.** These tests prove the platform's behaviour given
  model output; they say nothing about output *quality*. Prompt-quality regression
  needs a separate evaluation harness with recorded fixtures.
- **`pytest-timeout` is not installed.** Worth adding so a future deadlock like
  METRICS-01 fails fast instead of hanging CI.
