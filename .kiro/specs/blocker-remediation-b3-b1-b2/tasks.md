# Implementation Plan: Blocker Remediation B3 -> B1 -> B2

Order is mandatory: B3 -> verify -> B1 -> verify -> B2 -> verify -> regression -> re-audit.
No task may be marked complete without both an implementation change and a passing test.
Requirement numbers refer to the blocker brief (2.x = B3, 4.x = B1, 7.x = B2).

## Overview

Fixes the three BLOCKER findings from the Phase 1 audit in a dependency-forced order.
B3 lands first because B2's resume path loads a run from the database and B1's contract
tests need somewhere to record tool interactions. B1 second, because an approval that
resumes into a loop which cannot call tools proves nothing. B2 last, as it composes both.

Each phase ends in an explicit verification gate. A task is complete only when it has
both an implementation change and a passing regression test.

## Task Dependency Graph

```
0.1 (git baseline)
 |
 v
1.1 exceptions ──> 1.2 UnitOfWork ──┐
1.3 migration ──────────────────────┤
                                    v
                              1.4 AgentRepository
                                    |
                                    v
                              1.5 state machine requires repository
                                    |
                     ┌──────────────┴──────────────┐
                     v                             v
              1.6 API creates task+run      1.7 worker own session
                     └──────────────┬──────────────┘
                                    v
                              1.8 reads from DB
                                    v
                              1.9 B3 tests ──> 1.10 GATE B3
                                                   |
                                                   v
                    2.1 tool_contract ──> 2.2 to_tool_definition
                                                   |
                                                   v
                                          2.3 provider interface
                                                   |
                              ┌────────────────────┼────────────────────┐
                              v                    v                    v
                      2.4 anthropic          2.5 openai          2.6 factory raises
                              └────────────────────┼────────────────────┘
                                                   v
                                    2.7 authorization gate ──> 2.8 persist tool calls
                                                   v
                                          2.9 B1 tests ──> 2.10 GATE B1
                                                                 |
                                                                 v
                                          3.1 transition table ──> 3.2 split phases
                                                                 |
                                          ┌──────────────────────┤
                                          v                      v
                                 3.3 durable approval    3.5 durable resume
                                          v                      v
                                 3.4 idempotent claim    3.6 stalled-run reaper
                                          └──────────┬───────────┘
                                                     v
                                          3.7 B2 tests ──> 3.8 GATE B2
                                                                 |
                                                                 v
                                    4.1 E2E ──> 4.2 restart ──> 4.3 regression
                                                                 |
                                                                 v
                                                4.4 re-audit ──> 4.5 report
```

Machine-readable wave definitions (tasks in the same wave have no dependency on each
other and may be executed concurrently):

```json
{
  "waves": [
    { "wave": 1,  "tasks": ["0.1"],                 "depends_on": [] },
    { "wave": 2,  "tasks": ["1.1", "1.2", "1.3"],   "depends_on": ["0.1"] },
    { "wave": 3,  "tasks": ["1.4"],                 "depends_on": ["1.1", "1.2", "1.3"] },
    { "wave": 4,  "tasks": ["1.5"],                 "depends_on": ["1.4"] },
    { "wave": 5,  "tasks": ["1.6", "1.7"],          "depends_on": ["1.5"] },
    { "wave": 6,  "tasks": ["1.8"],                 "depends_on": ["1.6", "1.7"] },
    { "wave": 7,  "tasks": ["1.9"],                 "depends_on": ["1.8"] },
    { "wave": 8,  "tasks": ["1.10"],                "depends_on": ["1.9"], "gate": "B3" },
    { "wave": 9,  "tasks": ["2.1"],                 "depends_on": ["1.10"] },
    { "wave": 10, "tasks": ["2.2", "2.3"],          "depends_on": ["2.1"] },
    { "wave": 11, "tasks": ["2.4", "2.5", "2.6"],   "depends_on": ["2.3"] },
    { "wave": 12, "tasks": ["2.7"],                 "depends_on": ["2.4", "2.5", "2.6"] },
    { "wave": 13, "tasks": ["2.8"],                 "depends_on": ["2.7"] },
    { "wave": 14, "tasks": ["2.9"],                 "depends_on": ["2.8"] },
    { "wave": 15, "tasks": ["2.10"],                "depends_on": ["2.9"], "gate": "B1" },
    { "wave": 16, "tasks": ["3.1", "3.2"],          "depends_on": ["2.10"] },
    { "wave": 17, "tasks": ["3.3", "3.5"],          "depends_on": ["3.2"] },
    { "wave": 18, "tasks": ["3.4", "3.6"],          "depends_on": ["3.3", "3.5"] },
    { "wave": 19, "tasks": ["3.7"],                 "depends_on": ["3.4", "3.6"] },
    { "wave": 20, "tasks": ["3.8"],                 "depends_on": ["3.7"], "gate": "B2" },
    { "wave": 21, "tasks": ["4.1"],                 "depends_on": ["3.8"] },
    { "wave": 22, "tasks": ["4.2"],                 "depends_on": ["4.1"] },
    { "wave": 23, "tasks": ["4.3"],                 "depends_on": ["4.2"] },
    { "wave": 24, "tasks": ["4.4"],                 "depends_on": ["4.3"] },
    { "wave": 25, "tasks": ["4.5"],                 "depends_on": ["4.4"] }
  ]
}
```
Critical path: `0.1 -> 1.3 -> 1.4 -> 1.5 -> 1.6/1.7 -> 1.10 -> 2.3 -> 2.4 -> 2.10 -> 3.2 -> 3.5 -> 3.8 -> 4.3`.
Parallelisable: 1.1/1.2/1.3 are independent; 2.4/2.5/2.6 are independent once 2.3 lands.

## Tasks
### Phase 0 - Safety baseline

- [ ] 0.1 Establish version control before any source edit
  - Run `git init`, add a `.gitignore`-respecting initial commit of the current tree
  - Confirm `git status` is clean afterwards so every later change is a reviewable diff
  - Rationale: changes span agent core + API + worker + a migration with no rollback today
  - _Requirements: operating rules section 1_

### Phase 1 - B3 durable persistence

- [ ] 1.1 Add blocker exception types
  - Add `PersistenceError`, `PlanIntegrityError`, `RunClaimError` to `app/core/exceptions.py` as `DomainError` subclasses
  - Map `PlanIntegrityError` and `RunClaimError` to 409 in `app/core/exception_handlers.py`; `PersistenceError` to 500 with correlation id and no internal detail
  - _Requirements: 2.5, 2.8_

- [ ] 1.2 Create the worker unit of work
  - New `app/infrastructure/db/uow.py`: async context manager opening a session from `AsyncSessionLocal`, commit on success, rollback on exception, always close
  - Deliberately separate from `get_db` so request scope and worker scope cannot be confused
  - _Requirements: 2.4, 2.9_

- [ ] 1.3 Write the schema migration
  - New Alembic revision on top of `75fbe090f4f0`
  - `agent_plans.plan_hash`; `agent_runs.execution_mode/approved_by/approved_at/approved_plan_hash/sandbox_id/user_prompt`; `coding_tasks.session_id` + unique index; index `agent_runs(status, created_at)`
  - All additive and nullable-or-defaulted; implement a complete `downgrade()`
  - Verify with `alembic upgrade head --sql` (renders PostgreSQL DDL offline)
  - _Requirements: 2.3, 2.6, 2.7_

- [ ] 1.4 Extend AgentRepository
  - Add `get_run`, `latest_plan`, `load_run_aggregate`, `update_run_state_cas`, `increment_run_counters`, `record_approval`
  - `update_run_state_cas` uses `UPDATE ... WHERE id=:id AND status=:expected RETURNING id`
  - Fix the latent FK bug: `create_tool_call_and_result` must pass `step_id=None` rather than fabricating `uuid.uuid4()` for a missing step
  - _Requirements: 2.4, 2.5, 2.7_

- [ ] 1.5 Make persistence mandatory in the state machine
  - `AgentStateMachine.__init__`: `repository` becomes required (remove `= None`)
  - Remove the `if self.repository:` guards; let state-transition and plan persistence failures raise `PersistenceError`
  - Keep tool-result row failures non-fatal (log and continue) per the Error Handling table
  - Persist `plan_hash` when the plan is created
  - _Requirements: 2.1, 2.5, 2.6, 2.7_

- [ ] 1.6 Create durable records at the API boundary
  - `POST /sessions`: authenticate -> authorize project -> create `CodingTaskModel` -> create `AgentRunModel` -> commit -> enqueue `run_agent_session(run_id)`
  - On persistence failure, do not enqueue and do not start execution
  - _Requirements: 2.3, 2.5, 2.8_

- [ ] 1.7 Give the worker its own session and rehydration
  - `run_agent_session(run_id)` accepts only the durable identifier
  - Open `UnitOfWork`, load the run, claim it with `update_run_state_cas`, rehydrate the state machine, execute, commit
  - Never serialize a runtime object into the queue
  - _Requirements: 2.9, 2.4_

- [ ] 1.8 Move session reads onto the database
  - `GET /sessions/{id}` and the command endpoints resolve the run via `AgentRepository`, not `SESSIONS_DB`
  - Retire `SESSIONS_DB` / `STATE_MACHINES_DB` as authority
  - _Requirements: 2.1_

- [ ] 1.9 B3 regression tests
  - New `tests/blockers/test_b3_persistence.py` covering B3.1-B3.10
  - Register a `blocker` marker in `pytest.ini`
  - B3.4/B3.10 must rehydrate through a NEW session and NEW state machine from `run_id` alone, never by reusing the original object
  - B3.7 injects failure at the repository boundary and asserts execution does not continue
  - B3.9 asserts single-winner claim under `asyncio.gather`
  - _Requirements: 2.10_

- [ ] 1.10 B3 verification gate
  - Run the B3 tests, then the existing agent/database/api suites
  - Answer in the report: can a run be reconstructed from the DB after the creating process is gone? Can a worker load it from `run_id` alone? Does state survive restart?
  - Do not start B1 until these pass or a limitation is documented
  - _Requirements: section 3_

### Phase 2 - B1 AI tool execution contract

- [ ] 2.1 Define the canonical tool contract
  - New `app/domain/entities/tool_contract.py` with `ToolDefinition`, `ToolCallRequest`, `ToolExecutionOutcome`
  - _Requirements: 4.2, 4.5, 4.6_

- [ ] 2.2 Derive tool definitions from the existing schema source
  - `BaseTool.to_tool_definition()` built from `args_schema.model_json_schema()`
  - Re-implement `to_openai_schema()` as a renderer over it so the two cannot drift
  - _Requirements: 4.1, 4.2_

- [ ] 2.3 Type the provider interface
  - `AIProviderInterface.generate_response`/`stream_response`: `tools: Optional[List[ToolDefinition]]`
  - `LLMResponse.tool_calls: List[ToolCallRequest]`; add a structured tool-result channel to `LLMMessage`
  - _Requirements: 4.1, 4.2, 4.5_

- [ ] 2.4 Fix the Anthropic adapter (the actual B1 defect)
  - Render `ToolDefinition` -> `{"name","description","input_schema"}` and pass `tools=` to `messages.create`
  - Stop discarding `tool_calls`/`tool_call_id`; emit `tool_use` and `tool_result` content blocks
  - Parse `block.type == "tool_use"` into `ToolCallRequest` preserving `block.id`
  - Apply the same to `stream_response`
  - _Requirements: 4.3, 4.4, 4.5_

- [ ] 2.5 Fix the OpenAI adapter
  - Render `ToolDefinition` -> `{"type":"function","function":{...}}`
  - `stream_response` currently drops tools too; fix it
  - _Requirements: 4.7_

- [ ] 2.6 Stop silent provider substitution
  - `AIProviderFactory.get_provider` raises `ConfigurationError` for an unknown name instead of returning Anthropic
  - _Requirements: 4.7_

- [ ] 2.7 Make the authorization gate real and reachable
  - `ControlledToolLayer.execute_tool`: ordered gate - registry lookup, schema validation, `validate_permission`, `policy_engine.evaluate_tool_call` - all before dispatch
  - Thread the run initiator's `user_role` through from the state machine so `validate_permission` stops being inert
  - Re-raise `LimitExceededError` instead of swallowing it in the generic handler
  - Return typed `ToolExecutionOutcome`; a security refusal must never render as successful tool output
  - _Requirements: 4.4, 4.6, section 5_

- [ ] 2.8 Persist the tool interaction
  - Write `ToolCall` + `ToolResult` rows for every executed tool via the repository from Phase 1
  - _Requirements: 4.5, 2.7_

- [ ] 2.9 B1 regression tests
  - New `tests/blockers/test_b1_tool_contract.py` covering B1.1-B1.14
  - Extend `tests/support/providers.py` with a scripted fake provider: tool_use, plain text, multiple tool calls, malformed, timeout, error
  - Contract tests parametrized across every adapter so a third adapter cannot repeat B1
  - No network and no credentials required
  - _Requirements: 4.8_

- [ ] 2.10 B1 verification gate
  - Confirm: tool request received, identified, arguments validated, authorized, executed, result returned, invalid/unauthorized rejected, interaction persisted
  - Do not start B2 until these pass
  - _Requirements: section 6_

### Phase 3 - B2 approval resume

- [ ] 3.1 Add the state transition table
  - `_transition_to` validates against an explicit table; terminal states accept no outgoing transition
  - Add the missing `COMMITTING` state
  - Add state guards to `handle_user_cancellation` and `handle_modify_requirements`
  - _Requirements: 7.4_

- [ ] 3.2 Split the execution loop into resumable phases
  - `run_planning_phase()` ends by persisting plan + hash and the `AWAITING_APPROVAL` state
  - `run_implementation_phase()` runs IMPLEMENTING through terminal
  - Keep `run_autonomous_loop()` as a wrapper so existing callers and tests keep working
  - _Requirements: 7.6, 7.7_

- [ ] 3.3 Make approval durable and authorized
  - `POST /sessions/{id}/approve`: load run from DB, verify `AWAITING_APPROVAL`, verify plan hash, require project role >= MAINTAINER
  - Persist to `approval_audit_logs` and to the run's approval columns, then commit
  - _Requirements: 7.1, 7.2_

- [ ] 3.4 Make approval idempotent and concurrency safe
  - Claim with conditional `UPDATE ... WHERE status='AWAITING_APPROVAL'`; zero rows means already approved -> return 200 with the existing approval
  - Enqueue `resume_agent_session(run_id)` only after the commit succeeds
  - _Requirements: 7.5, 7.6_

- [ ] 3.5 Implement durable resume in the worker
  - `resume_agent_session(run_id)`: own `UnitOfWork`, load run and approved plan, verify state, verify approval, re-verify plan hash, then `run_implementation_phase()`
  - Plan hash mismatch raises `PlanIntegrityError` and fails the run without executing a tool
  - _Requirements: 7.3, 7.7_

- [ ] 3.6 Add stalled-run recovery
  - `reap_stalled_runs` beat task re-enqueues runs left non-terminal past a threshold
  - Covers "approval persisted but worker never started" and "worker died after approval"
  - _Requirements: 7.8_

- [ ] 3.7 B2 regression tests
  - New `tests/blockers/test_b2_approval_resume.py` covering B2.1-B2.18
  - B2.11/B2.12 rebuild from `run_id` after discarding the original objects
  - B2.14 fires concurrent approvals and asserts exactly one resume enqueued
  - B2.15 mutates the persisted plan after approval and asserts execution is refused
  - _Requirements: 7.9_

- [ ] 3.8 B2 verification gate
  - Confirm approval durably resumes execution and survives restart and concurrency scenarios
  - _Requirements: section 13_

### Phase 4 - Integration and regression

- [ ] 4.1 End-to-end blocker flow test
  - New `tests/blockers/test_blocker_e2e.py`: user -> project -> task -> run -> plan -> AWAITING_APPROVAL -> approval -> worker resume -> provider -> tool authorization -> tool execution -> result -> test -> review -> terminal state
  - Assert every stage, including durable rows at each boundary
  - _Requirements: section 8_

- [ ] 4.2 Process restart and failure tests
  - New `tests/blockers/test_process_restart.py` covering cases A-F: API restart before/after approval, worker restart after approval, worker failure during implementation, provider failure, database persistence failure
  - _Requirements: section 9_

- [ ] 4.3 Full regression
  - Run in order: blocker tests, unit, integration, api, database, security, the existing `vuln` suite, then the whole mandatory selector
  - Run `ruff check`, `mypy`, frontend `tsc`/`vitest`/`build`
  - If any `vuln` xfail now XPASSes because of a blocker fix, remove that marker deliberately and record the evidence; do not leave `strict=True` failing
  - Report exact counts; do not fabricate
  - _Requirements: section 10_

- [ ] 4.4 Independent blocker re-audit
  - Re-read the implementation as if written by someone else; verify B3, B1, B2 against source rather than comments or test names
  - Search for surviving bypass paths: remaining in-memory authority, `if self.repository`, adapters dropping tools, resume paths depending on process memory
  - Update the Phase 1 finding matrix with current status
  - _Requirements: section 11_

- [ ] 4.5 Write the blocker remediation report
  - Per-blocker status, files changed, tests added, tests passed, remaining limitations
  - Mark anything not executed as CODE FIXED / RUNTIME UNVERIFIED, including PostgreSQL concurrency and any Docker-dependent stage
  - List any blocker that remains unresolved; do not claim production readiness
  - _Requirements: section 12_

## Notes

### Runtime limitations (stated before starting, not discovered later)

- **No Docker daemon** on this machine (`docker` is not on PATH). Anything requiring a
  real container - sandbox execution, the compose stack, the CI E2E stage - will be
  reported as CODE FIXED / RUNTIME UNVERIFIED.
- **No local PostgreSQL.** Tests run against the existing file-backed SQLite fixture in
  `tests/conftest.py`. That validates ORM wiring, transactions, FK declarations and the
  resume path, but not PostgreSQL-specific behaviour: real FK enforcement semantics or
  `RETURNING` under genuine concurrent load.
- Consequently tasks 1.9 (B3.9) and 3.7 (B2.14) prove the CAS logic is single-winner
  under `asyncio.gather` but cannot prove multi-process contention. Those remain
  RUNTIME UNVERIFIED until CI runs them against the PostgreSQL service container
  already configured in `.github/workflows/pr.yml` stage 6.
- The migration is verified by `alembic upgrade head --sql`, which proves it renders
  valid PostgreSQL DDL, not that it executed against a live database.

### Tooling constraint

File-writing tools are not exposed in this session, so edits are applied via shell
string replacement against exact anchors, each guarded to report when an anchor is not
found. Every change is verified by re-reading the file and running `ruff`, `mypy` and
the test suite. This is slower than a normal edit path and is the main reason task 0.1
(version control) matters: it gives a reviewable diff of everything touched.

### Scope discipline

Four adjacent fixes are in scope because a blocker cannot be correct without them, and
each is named in the design with its justification:

1. `create_tool_call_and_result` fabricating a random `step_id` (FK violation) - task 1.4
2. `AIProviderFactory` silently falling back to Anthropic - task 2.6
3. `user_role` never threaded, making `validate_permission` inert - task 2.7
4. Missing terminal-state guards - task 3.1

Everything else stays in the Phase 1 finding matrix. In particular the broader C2 work
(command allowlist replacing the substring blocklist, per-call plan-hash
re-verification) is Phase 3 of the overall remediation, not this spec. This spec only
makes the policy gate exist and be reachable.

### Test integrity rules

No new `skip`, no new `xfail`, no deleted or weakened security test. The 103 existing
`vuln` markers stay as they are. If a blocker fix incidentally makes one pass,
`strict=True` will surface it as a failure - that marker is then removed deliberately,
with evidence recorded in task 4.3, never left red or re-hidden.

