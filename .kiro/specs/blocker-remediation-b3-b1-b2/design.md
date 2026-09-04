# Design: Blocker Remediation B3 -> B1 -> B2

## Overview

Three blockers from the Phase 1 audit, fixed in a mandatory order. The order is
forced by real dependencies, not preference:

- **B3** (durable persistence) must land first because B2's resume path loads a run
  from the database, and B1's contract tests need somewhere to record tool
  interactions.
- **B1** (tool execution contract) second, because an approval that resumes into a
  loop which cannot call tools proves nothing.
- **B2** (approval resume) last, as it composes both.

Scope discipline: this design fixes only B3, B1 and B2. Adjacent findings are
touched **only** where a blocker fix cannot be correct without them, and each such
case is called out explicitly. Everything else stays in the Phase 1 finding matrix.

### What is actually broken (verified in Phase 1)

| Blocker | Verified root cause |
| --- | --- |
| B3 | `AgentStateMachine.__init__` takes `repository: Optional[AgentRepository] = None`; both production entry points omit it, and all 6 persistence call sites are wrapped in `if self.repository:` with `except Exception: logger.warning(...)`. Making durability optional at the constructor made it optional in production. |
| B1 | `AIProviderInterface.generate_response(tools: Optional[List[Dict[str, Any]]])` is an untyped, optional parameter with no contract test. `OpenAIAdapter` honours it because OpenAI's wire format matches the internal format 1:1; `AnthropicAdapter` (the default provider) accepts and discards it because Anthropic's format differs and the translation was never written. Both `stream_response` implementations discard it too. |
| B2 | The approval pause is `return self.run.execution_summary` at `state_machine.py:277`. `handle_user_approval` mutates in-memory state and returns. `run_autonomous_loop` has exactly two call sites, neither reachable from `/approve`. |

---

## Guiding constraints

1. **The database is the only authoritative store.** In-memory structures may
   remain as a cache, never as the source of truth.
2. **No request-scoped session in a long-running worker.** FastAPI closes a
   `Depends(get_db)` session before background tasks run (>=0.106), so the worker
   opens its own.
3. **Persistence failure fails the run.** The current `except Exception:
   logger.warning(...)` pattern is the reason B3 is invisible. It is replaced by
   fail-closed behaviour on the transitions that matter.
4. **The model is not an authorization authority.** Parse -> validate -> authorize
   -> policy -> execute, enforced in application code immediately before dispatch.
5. **No test weakening.** No new `skip`, no new `xfail`, no deleted security test.
   The 103 existing `vuln` markers stay as they are; if a blocker fix incidentally
   makes one pass, `strict=True` surfaces it and we remove that marker deliberately
   with evidence.
6. **Reuse existing structures.** `AgentRepository` already implements `create_run`,
   `update_run_state`, `create_plan`, `create_step`, `create_tool_call_and_result`,
   `create_error`. We extend it; we do not replace it.

---

## Architecture

### Current runtime path (broken)

```
POST /sessions ──> AgentStateMachine(repository=None)
                        │
                        ├─ SESSIONS_DB[id]        in-process dict = ONLY state
                        └─ BackgroundTasks ──> run_autonomous_loop()
                                                    │
                                                    ├─ plan ──> return  ◀── B2 dead end
                                                    └─ provider.generate_response(tools=…)
                                                             └─ Anthropic drops tools ◀── B1
```

Nothing durable. Restart loses everything; `/approve` only works on the process that
served the create.

### Target runtime path

```
POST /sessions
   authenticate ─> authorize ─> CodingTask ─> AgentRun ─> COMMIT
                                                            │
                                    enqueue(run_id) ────────┘   durable id only
                                            │
                      Celery worker ─── UnitOfWork(own session)
                                            │
                                   load run from DB (rehydrate)
                                            │
                            claim via conditional UPDATE (at-most-once)
                                            │
                              run_planning_phase()
                                            │
                          persist plan + plan_hash ─> AWAITING_APPROVAL ─> COMMIT
                                            │
                                         [ pause ]
                                            │
POST /approve ─ authz ─ load ─ verify state ─ verify hash ─ persist approval
                                            │
                              claim AWAITING_APPROVAL ─> IMPLEMENTING ─> COMMIT
                                            │
                                 enqueue resume(run_id)
                                            │
                      Celery worker ─── UnitOfWork(own session)
                                            │
                                re-verify plan_hash  ◀── fail closed
                                            │
                            run_implementation_phase()
                              │
                              ├─ provider.generate_response(tools=[ToolDefinition])
                              │        └─ per-provider render ─> tools reach model
                              ├─ parse ─> ToolCallRequest
                              ├─ validate ─> authorize ─> policy ─> execute
                              └─ persist ToolCall + ToolResult each iteration
                                            │
                              TESTING ─> DEBUGGING ─> REVIEWING ─> COMMITTING
                                            │
                                   COMPLETED / FAILED   (persisted)
```

Every horizontal `COMMIT` is a durable boundary: a crash after it is recoverable, a
crash before it leaves no partial run.

### Layering rules preserved

`AgentStateMachine` stays in `application/` and never imports `infrastructure/db`
directly - it depends on the `AgentRepository` passed to it. The provider contract
types live in `domain/entities/tool_contract.py` so both `application/` and
`infrastructure/ai_providers/` can depend on them without either depending on the
other.

## Components and Interfaces

### New

| Component | File | Responsibility |
| --- | --- | --- |
| `UnitOfWork` | `app/infrastructure/db/uow.py` | async CM: own session from `AsyncSessionLocal`, commit/rollback/close. Worker-scoped, never request-scoped. |
| `ToolDefinition`, `ToolCallRequest`, `ToolExecutionOutcome` | `app/domain/entities/tool_contract.py` | provider-neutral canonical tool contract |
| `PersistenceError`, `PlanIntegrityError`, `RunClaimError` | `app/core/exceptions.py` (add) | distinguish storage / integrity / concurrency failures from agent failures |
| `reap_stalled_runs` | `app/worker/tasks.py` (add) | beat task re-enqueueing non-terminal runs with no live worker |

### Changed signatures

```python
# app/infrastructure/db/repositories/agent_repository.py
async def get_run(run_id: uuid.UUID) -> Optional[AgentRunModel]
async def load_run_aggregate(run_id) -> Optional[RunAggregate]      # run + latest plan
async def update_run_state_cas(run_id, expected: str, new: str, **fields) -> bool
async def increment_run_counters(run_id, *, prompt=0, completion=0, total=0) -> None
async def record_approval(run_id, approver_id, plan_hash) -> None
async def latest_plan(run_id) -> Optional[AgentPlanModel]

# app/domain/interfaces/ai_provider.py
tools: Optional[List[ToolDefinition]] = None          # was List[Dict[str, Any]]
LLMResponse.tool_calls: List[ToolCallRequest]         # was List[Dict[str, Any]]

# app/infrastructure/tools/base.py
def to_tool_definition(self) -> ToolDefinition        # new canonical source
def to_openai_schema(self) -> Dict[str, Any]          # now renders from the above

# app/application/agent/state_machine.py
def __init__(..., repository: AgentRepository, ...)    # REQUIRED, no default
async def run_planning_phase(self) -> Dict[str, Any]
async def run_implementation_phase(self) -> Dict[str, Any]
async def run_autonomous_loop(self) -> Dict[str, Any]  # retained wrapper

# app/worker/tasks.py
def run_agent_session(run_id: str)                     # durable id only
def resume_agent_session(run_id: str)
```

### Unchanged on purpose

`ControlledToolLayer.execute_tool` keeps its 8-step shape and its signature; B1 adds
the policy call and threads `user_role`. `PathValidator`, `SandboxSecurityPolicy` and
`LocalGitProvider` are untouched - they are not blocker surface.
## B3 - Durable Persistence

### ADR-1: the CodingTask ownership problem

`AgentRunModel.task_id` is `NOT NULL` with `ForeignKey("coding_tasks.id", ondelete="CASCADE")`.
`AgentRepository.create_run` does `task_id=uuid.UUID(run.task_id)`, and `run.task_id`
is currently the **session id** - a value that exists in no table. **No code path
anywhere creates a `coding_tasks` row.** So simply passing a repository into the
state machine raises a foreign-key violation, which the existing `except Exception`
would swallow - the failure would stay invisible.

Options considered:

| Option | Verdict |
| --- | --- |
| A. Make `task_id` nullable | Rejected. Discards the run/task/project lineage that makes runs attributable, and `agent_runs` loses its cascade path. |
| B. Auto-create a synthetic CodingTask inside the state machine | Rejected. Puts a persistence concern in the domain layer and hides task creation from the API contract. |
| **C. The API creates a CodingTask before starting a run** | **Chosen.** Matches the declared schema, keeps the state machine free of DB concerns, makes the durable chain explicit at the boundary that already validates the project. |

Chosen flow for `POST /api/v1/sessions`:

```
authenticate  -> get_current_user
authorize     -> ProjectService.get_project_by_id(required_role=MEMBER)
create        -> CodingTaskModel   (project_id, creator_id, prompt, status=PENDING)
create        -> AgentRunModel     (task_id = the row above, status=RECEIVED)
commit        --------------------  durable boundary
enqueue       -> Celery run_agent_session(run_id)   [durable identifier only]
respond       -> 202 with session/run id
```

If the commit fails, no run is enqueued and the caller receives an error.
Execution never starts for a run that does not exist.

### Changes

**`app/infrastructure/db/repositories/agent_repository.py`**

- Add `get_run(run_id) -> Optional[AgentRunModel]`.
- Add `load_run_aggregate(run_id)` returning the run plus its latest plan, so the
  worker can rehydrate without touching in-memory state.
- Add `update_run_state_cas(run_id, expected_status, new_status, **fields)` - a
  conditional `UPDATE ... WHERE id = :id AND status = :expected RETURNING id`.
  Replaces the read-modify-write in `update_run_state` for transitions where losing
  an update matters, and is the primitive B2 reuses for idempotency.
- Add `increment_run_counters(...)` using `SET col = col + :delta` so concurrent
  writers do not lose token counts.
- **Fix a latent FK bug found while designing this:** `create_tool_call_and_result`
  currently does `step_id=uuid.UUID(tool_call.step_id) if tool_call.step_id else uuid.uuid4()`.
  When `step_id` is absent it invents a random UUID referencing no `agent_steps`
  row, violating the `tool_calls.step_id` foreign key. Dormant only because the
  repository is never used. Must be `None`, not a fabricated UUID.
  *(In scope: B3 cannot be correct while this is present.)*

**New: `app/infrastructure/db/uow.py`** - an async context manager that opens a
session from `AsyncSessionLocal`, commits on success, rolls back on exception, and
always closes. This is what the worker uses. Deliberately separate from `get_db` so
request scope and worker scope cannot be confused.

**`app/application/agent/state_machine.py`**

- `repository` becomes a **required** constructor argument. Removing the `None`
  default is the structural fix: an unpersisted run becomes impossible to
  construct, so this class of regression cannot recur silently.
- Remove the `if self.repository:` guards. Persistence exceptions propagate for
  state transitions and plan writes (fail closed). For individual tool-result rows a
  failure is logged and the run continues, because losing one audit row must not
  destroy a healthy run - but the run's *state* is never allowed to diverge from the
  database.
- Add `PersistenceError` so a storage failure is distinguishable from an agent
  failure in the failure report.

**`app/api/v1/endpoints/sessions.py`**

- `create_agent_session` performs the ADR-1 flow and enqueues by `run_id`.
- Read and command endpoints resolve the run from the database instead of
  `SESSIONS_DB`.
- `SESSIONS_DB` / `STATE_MACHINES_DB` are removed as authority; the in-process
  `run_agent_background_task` path is retired in favour of the queue, which is what
  makes state survive a restart.

**`app/worker/tasks.py`** - `run_agent_session(run_id)` takes only the durable
identifier, opens its own session via the UoW, rehydrates the run, and executes. No
runtime object is ever serialized into the queue.

### Transaction boundaries

Each state transition is its own committed transaction: validate -> update ->
commit. Sandbox creation (an external side effect) happens **after** the run row is
committed, so a crash between them leaves a recoverable `RECEIVED` run rather than
an orphaned container. Sandbox cleanup already has an independent reaper.

### Concurrency (B3.9 - two workers, one run)

`update_run_state_cas` is the guard. A worker claims a run by transitioning
`RECEIVED -> ANALYZING` (or `AWAITING_APPROVAL -> IMPLEMENTING` on resume)
conditionally; if zero rows are affected another worker already claimed it, and this
one exits without executing. At-most-once execution without a distributed lock.

---

## B1 - AI Tool Execution Contract

### ADR-2: canonical contract, then per-provider adapters

The root cause is that the *internal* representation is OpenAI's wire format. Any
provider whose format differs must translate, and nothing forced that to happen. The
fix makes the internal representation provider-neutral so dropping tools becomes a
type error rather than a silent omission.

**New: `app/domain/entities/tool_contract.py`**

```python
class ToolDefinition(BaseModel):      # canonical, provider-neutral
    name: str
    description: str
    input_schema: Dict[str, Any]      # JSON Schema object

class ToolCallRequest(BaseModel):     # canonical parsed model request
    id: str                           # provider tool-use id, preserved verbatim
    name: str
    arguments: Dict[str, Any]

class ToolExecutionOutcome(str, Enum):
    SUCCESS, INVALID_TOOL, INVALID_ARGUMENTS, UNAUTHORIZED,
    POLICY_DENIED, EXECUTION_FAILED, SANDBOX_FAILED, TIMEOUT, PROVIDER_ERROR
```

`ToolExecutionOutcome` answers requirement 4.6: the categories are distinct values,
so a security refusal can never be rendered as successful tool output.

**`app/infrastructure/tools/base.py`** - add `to_tool_definition() -> ToolDefinition`
built from `args_schema.model_json_schema()` (the existing canonical source).
`to_openai_schema()` is retained but re-implemented as a renderer over
`to_tool_definition()`, so the two cannot drift.

**`app/domain/interfaces/ai_provider.py`** - the contract change:

```python
async def generate_response(
    self,
    messages: List[LLMMessage],
    tools: Optional[List[ToolDefinition]] = None,   # was List[Dict[str, Any]]
    ...
) -> LLMResponse
```

`LLMResponse.tool_calls` becomes `List[ToolCallRequest]`. `LLMMessage` gains a
structured tool-result channel so tool output stops travelling as a `role="user"`
string.

**`app/infrastructure/ai_providers/anthropic_adapter.py`** - the actual B1 fix:

- Render `ToolDefinition` -> Anthropic `{"name", "description", "input_schema"}` and
  pass `tools=` to `messages.create`.
- Stop discarding `tool_calls` / `tool_call_id` in the message reformatter; emit
  proper `tool_use` and `tool_result` content blocks.
- Parse `block.type == "tool_use"` into `ToolCallRequest`, preserving `block.id`.
- Apply the same to `stream_response`.

**`app/infrastructure/ai_providers/openai_adapter.py`** - render `ToolDefinition` ->
`{"type": "function", "function": {...}}`; fix `stream_response`, which also drops
tools.

**`provider_factory.py`** - raise `ConfigurationError` for an unknown provider
instead of silently returning Anthropic. *(In scope: a test asserting "Anthropic
receives tools" is meaningless if an unknown name silently becomes Anthropic.)*

### Authorization flow

Enforced in `ControlledToolLayer.execute_tool`, in this order, before any dispatch:

```
ToolCallRequest
  -> registry.get_tool(name)                 unknown     -> INVALID_TOOL
  -> tool.validate_inputs(arguments)         schema fail -> INVALID_ARGUMENTS
  -> validate_permission(perm, user_role)    role fail   -> UNAUTHORIZED
  -> policy_engine.evaluate_tool_call(...)   high risk   -> POLICY_DENIED
  -> dispatch inside sandbox with timeout
  -> persist ToolCall + ToolResult (B3)
```

Two scope notes. `user_role` is currently never passed, making `validate_permission`
inert; B1 threads the run initiator's role through, because B1.7 (unauthorized tool
rejected) cannot otherwise be tested. Wiring `evaluate_tool_call` is the minimum
needed for B1.8 (policy-denied). The broader C2 work - command allowlist replacing
the substring blocklist, per-call plan-hash re-verification - stays in Phase 3; this
design only makes the gate *exist* and be *reachable*.

---

## B2 - Approval Resume

### ADR-3: suspension is a persisted state, not a function return

Today the pause is `return self.run.execution_summary`, so resumption would require
re-entering a coroutine that has already exited. The fix is to stop modelling
suspension as control flow and model it as a persisted state that a fresh worker can
pick up.

`run_autonomous_loop` is split into two independently callable phases:

| Method | Covers | Ends at |
| --- | --- | --- |
| `run_planning_phase()` | RECEIVED -> ANALYZING -> PLANNING -> AWAITING_APPROVAL | persists plan + hash, returns |
| `run_implementation_phase()` | IMPLEMENTING -> TESTING -> DEBUGGING -> REVIEWING -> COMMITTING -> COMPLETED | terminal state |

`run_autonomous_loop()` is kept as a thin wrapper (planning, then implementation if
mode is AUTONOMOUS) so existing callers and tests keep working.

### Durable approval flow

```
POST /api/v1/sessions/{id}/approve
  authenticate            get_current_user
  authorize               run -> task -> project, membership >= MAINTAINER
  load                    AgentRepository.get_run(run_id)        [from DB]
  verify state            status == AWAITING_APPROVAL             else 409
  verify plan integrity   sha256(plan_markdown) == stored hash    else 409, fail closed
  persist approval        INSERT approval_audit_logs (approver, ts, hash, action)
  claim atomically        UPDATE ... WHERE status='AWAITING_APPROVAL' -> 'IMPLEMENTING'
                          RETURNING id      0 rows => already approved, return 200 idempotent
  commit                  ---------------- durable boundary
  enqueue                 resume_agent_session(run_id)
  respond                 202
```

Authorization note: approval currently accepts the run owner **or** an admin and
never checks `approver_role`. This design requires project role >= MAINTAINER, so the
approver's authority is actually verified. Separation of duties (initiator may not
approve their own high-risk run) is a policy question deferred to Phase 3; it is
recorded here so it is not lost.

### Plan integrity (B2.8, B2.15)

`AgentPlanModel` has no hash column today, and `approved_plan_hash` is computed in
memory and never compared. Design:

1. `run_planning_phase` computes `sha256` over the canonical plan markdown and
   persists it on the plan row.
2. Approval recomputes it from the stored plan and compares before accepting.
3. `run_implementation_phase` **re-verifies** it after loading, before the first
   tool call. Mismatch -> `PlanIntegrityError` -> FAILED, no execution.

Step 3 is what makes B2.15 real: a plan mutated between approval and resume is
rejected at the point of use, not merely at the point of approval.

### Idempotency and concurrency (B2.13, B2.14)

The conditional UPDATE is the single serialization point. Two simultaneous approvals
both pass the read checks; only one affects a row. The loser returns 200 with the
existing approval rather than an error, so a double-clicked button is harmless, and
exactly one resume job is enqueued.

### Crash recovery (B2.16, cases 1-5)

State is committed **before** the job is enqueued, so the failure mode is a run in
`IMPLEMENTING` with no worker - recoverable, not lost. A `reap_stalled_runs` beat
task (alongside the existing sandbox reaper) re-enqueues runs left in a non-terminal
state past a threshold. This covers "approval persisted but worker never started"
and "worker died after approval" with one mechanism.

### State guards

`_transition_to` gains a transition table. Terminal states (COMPLETED, FAILED,
CANCELLED) accept no outgoing transitions. This closes the Phase 1 finding that
`handle_user_cancellation` and `handle_modify_requirements` have no state guard and
can rewrite a finished run. *(In scope: B2.17/B2.18 require it.)*

A `COMMITTING` state is added - it is in the required state list and currently does
not exist, so commit/push happen outside the state machine and are invisible in run
history.

---

## Data Models

### Existing entities reused (no duplicates created)

| Entity / model | Role in this design | Change |
| --- | --- | --- |
| `CodingTaskModel` | durable parent of a run; satisfies the `agent_runs.task_id` FK | **now actually written** + `session_id` column |
| `AgentRunModel` | authoritative run state | + `execution_mode`, `approved_by`, `approved_at`, `approved_plan_hash`, `sandbox_id`, `user_prompt` |
| `AgentPlanModel` | the plan under approval | + `plan_hash` |
| `AgentStepModel` | state-transition history | unchanged (already has `uq_run_step_number`) |
| `ToolCallModel` / `ToolResultModel` | tool audit | unchanged schema; **FK bug fixed in the repository** |
| `ErrorLogModel` | failures incl. `PersistenceError` | unchanged |
| `ApprovalAuditModel` | immutable approval record | **now actually written** |
| `AgentRun` / `AgentStep` / `AgentPlan` (domain dataclasses) | in-memory working state | unchanged shape; now always mirrored to DB |

Domain dataclasses in `app/domain/entities/agent.py` already carry
`approved_by`, `approved_at`, `approved_plan_hash` and `high_risk_approved` - Phase 1
found them written and never read. This design gives them a durable home rather than
inventing new fields.
### Migration plan

One Alembic revision on top of `75fbe090f4f0`:

| Change | Reason |
| --- | --- |
| `agent_plans.plan_hash VARCHAR(64) NULL` + index | B2 plan integrity |
| `agent_runs.execution_mode VARCHAR(50) NOT NULL DEFAULT 'APPROVAL_REQUIRED'` | resume must know the mode without in-memory state |
| `agent_runs.approved_by UUID NULL FK users.id ON DELETE SET NULL`, `approved_at TIMESTAMPTZ NULL`, `approved_plan_hash VARCHAR(64) NULL` | durable approval on the run |
| `agent_runs.sandbox_id VARCHAR(255) NULL` | reattach or reap after restart |
| `agent_runs.user_prompt TEXT NOT NULL DEFAULT ''` | rehydrate without the original request |
| `coding_tasks.session_id UUID NULL` + unique index | map external session id -> task |
| Index `agent_runs(status, created_at)` | stalled-run reaper query |

Additive and nullable-or-defaulted only, so it is safe on a populated table and does
not need the expand/contract procedure. `downgrade()` reverses each change.

---

## Correctness Properties

Invariants the implementation must uphold. Each is independently testable and maps to
a named test from the required list.

> Requirement numbers below refer to the numbered sections of the blocker remediation
> brief (2.x = B3 durable persistence, 4.x = B1 tool contract, 7.x = B2 approval
> resume). This spec was started design-first, so there is no separate
> requirements.md; the brief is the requirements source.

### Property 1: A run always has a real parent task

No `agent_runs` row may reference a `coding_tasks` id that does not exist.
**Enforced by** the API creating the task inside the same transaction as the run,
plus the existing NOT NULL foreign key. **Test** B3.2.
**Validates: Requirements 2.3**

### Property 2: An unpersisted state machine cannot be constructed

`AgentStateMachine(...)` without a repository must raise `TypeError` at construction.
**Enforced by** removing the `= None` default. This makes the B3 regression class
structurally impossible rather than merely fixed. **Test** B3.7.
**Validates: Requirements 2.5**

### Property 3: Database status equals authoritative run state

After any state transition returns, a fresh read of `agent_runs.status` equals the
in-memory state. **Enforced by** commit-per-transition with no `if self.repository`
guard and no swallowed exception. **Tests** B3.3, B3.4.
**Validates: Requirements 2.6**

### Property 4: A run is reconstructable from its id alone

Given only `run_id`, a new session and new state machine reproduce state, plan,
execution mode and history. **Enforced by** `load_run_aggregate` plus rehydration.
**Tests** B3.4, B3.10, B2.10, B2.11, B2.12.
**Validates: Requirements 2.7**

### Property 5: At most one worker executes a run

Concurrent claim attempts result in exactly one executing worker. **Enforced by**
`UPDATE ... WHERE status = :expected RETURNING id`; zero rows means another worker
won. **Tests** B3.9, B2.14.
**Validates: Requirements 2.9**

### Property 6: Tools always reach the provider

For every adapter, tools passed to `generate_response` appear in the outbound
provider request. **Enforced by** typed `ToolDefinition` plus a contract test
parametrized across all adapters, which is what stops a third adapter repeating B1.
**Tests** B1.1, B1.2, B1.14.
**Validates: Requirements 4.1**

### Property 7: No tool executes before all gates pass

Execution is unreachable unless tool lookup, schema validation, permission check and
policy evaluation all succeed, in that order. **Enforced by** the ordered gate in
`execute_tool`. **Tests** B1.6, B1.7, B1.8, B1.9.
**Validates: Requirements 4.4**

### Property 8: Every executed tool call is persisted

For each executed tool there is exactly one `tool_calls` row and one `tool_results`
row. **Enforced by** a repository write per iteration. **Tests** B3.6, B1.10.
**Validates: Requirements 4.5**

### Property 9: Execution never proceeds on a tampered plan

If the stored plan hash differs from the approved hash, no tool executes.
**Enforced by** re-verification after load in `run_implementation_phase`, not only at
approval time. **Tests** B2.8, B2.15.
**Validates: Requirements 7.3**

### Property 10: Approval is idempotent

N identical approvals produce one approval record and one resume job; extra calls
return 200 with the existing approval. **Enforced by** the conditional UPDATE as the
single serialization point. **Tests** B2.13, B2.14.
**Validates: Requirements 7.5**

### Property 11: Terminal states are terminal

COMPLETED, FAILED and CANCELLED accept no outgoing transition. **Enforced by** the
transition table in `_transition_to`. **Tests** B2.17, B2.18.
**Validates: Requirements 7.4**

### Property 12: Approval is durable before work is scheduled

The approval and the new state are committed before any job is enqueued, so a crash
between them leaves a recoverable run rather than a lost one. **Enforced by** commit
ordering plus `reap_stalled_runs`. **Tests** B2.5, B2.16.
**Validates: Requirements 7.6**

## Error Handling

### Fail-closed vs fail-open, decided explicitly

| Failure | Behaviour | Rationale |
| --- | --- | --- |
| Run/task/plan persistence fails | **fail closed** - `PersistenceError`, run does not start or is marked FAILED | the whole point of B3; a run that is not recorded must not execute |
| State-transition persistence fails | **fail closed** | otherwise DB state diverges from reality, which is the bug being fixed |
| Single `ToolResult` row fails to persist | log + continue | losing one audit row must not destroy a healthy run; state integrity is unaffected |
| Plan hash mismatch on resume | **fail closed** - `PlanIntegrityError` -> FAILED | approved-plan tampering |
| Run claim loses the race | exit quietly, no execution | duplicate-execution prevention, not an error |
| Unknown / unauthorized / policy-denied tool | **fail closed** - typed `ToolExecutionOutcome`, refusal fed back to the model as a refusal | a security decision must never render as successful tool output |
| Provider error / timeout | surfaced as `PROVIDER_ERROR` / `TIMEOUT`; run FAILED with a distinguishable reason | C7 adds retry later; B1 only guarantees it is not mistaken for success |
| Malformed provider tool response | **fail closed** - no fabricated `ToolCallRequest` | B1.11 |

### Exception taxonomy

`PersistenceError`, `PlanIntegrityError` and `RunClaimError` are added to
`app/core/exceptions.py` as `DomainError` subclasses, so the existing
`domain_exception_handler` maps them without new handler wiring. `PlanIntegrityError`
maps to 409, `RunClaimError` to 409, `PersistenceError` to 500 with a correlation id
and no internal detail.

Note on an existing defect this design must not inherit: `ControlledToolLayer` today
catches `LimitExceededError` in its generic `except Exception` and returns it as a
failed tool result, so the run continues past its budget (Phase 1 finding M18). The
B1 rework re-raises limit errors rather than swallowing them.
## Testing Strategy

New files, mapped to the required IDs:

| File | Covers |
| --- | --- |
| `tests/blockers/test_b3_persistence.py` | B3.1-B3.10 |
| `tests/blockers/test_b1_tool_contract.py` | B1.1-B1.14 |
| `tests/blockers/test_b2_approval_resume.py` | B2.1-B2.18 |
| `tests/blockers/test_blocker_e2e.py` | section 8 end-to-end |
| `tests/blockers/test_process_restart.py` | section 9 cases A-F |
| `tests/support/providers.py` (extend) | scripted fake provider: tool_use, text, malformed, timeout, error |

Markers: `blocker` (new, registered in `pytest.ini`) plus existing `integration`,
`database`, `agent`, `security`. Added to the mandatory CI selector, so these gate
merges.

Key techniques:

- **Restart simulation** without killing processes: build a *new* session and a *new*
  `AgentStateMachine` from `run_id` alone, asserting the reconstructed run matches.
  A test that only reuses the original object proves nothing.
- **Provider contract tests run against every adapter** via parametrization, so
  Anthropic and OpenAI are held to the same contract - this is what prevents B1
  recurring in a third adapter.
- **No network.** The fake provider is scripted; no credential is required.
- B3.7 (persistence failure) and F (DB failure) inject failure at the repository
  boundary and assert the run does not silently continue.

---

## Runtime verification limits

Stated plainly, per the operating rules:

- **No Docker daemon on this machine** (verified: `docker` is not on PATH). Anything
  requiring a real container - sandbox execution, the compose stack, the CI E2E stage
  - will be **CODE FIXED / RUNTIME UNVERIFIED**.
- **PostgreSQL** is likewise unavailable locally. Tests run against the existing
  file-backed SQLite fixture. That validates ORM wiring, transactions, FK
  declarations and the resume path, but **not** PostgreSQL-specific behaviour: real
  FK enforcement semantics, `RETURNING` under concurrent load, or the migration
  against Postgres. The migration will be verified by offline SQL rendering
  (`alembic upgrade head --sql`), which proves it *compiles* for Postgres, not that
  it *ran*.
- Genuine concurrency (B3.9, B2.14) cannot be fully proven on SQLite, whose locking
  differs. Tests will assert the CAS logic is correct and single-winner under
  `asyncio.gather`; true multi-process contention is **RUNTIME UNVERIFIED** until CI
  runs it against the PostgreSQL service container already configured in
  `.github/workflows/pr.yml` stage 6.

## Risks

| Risk | Mitigation |
| --- | --- |
| **No version control** - these changes span the agent core, API and worker with no rollback | `git init` + baseline commit before any edit. Strongly recommended as step 0. |
| Making `repository` required breaks existing constructor calls | Only 3 call sites (2 production, 1 test). Compiler-visible, not silent. |
| Retiring `SESSIONS_DB` changes response timing to 202/async | Existing session tests are already quarantined for unrelated auth reasons; they get rewritten as part of B2 rather than patched around. |
| Splitting the loop could regress AUTONOMOUS mode | `run_autonomous_loop` wrapper preserved; existing agent tests must stay green. |
| Scope creep into C1/C2/C3 | Each in-scope adjacent fix is named above with its justification. Anything unnamed stays in the Phase 1 matrix. |
