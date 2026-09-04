# Business Logic Report

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  
**Core Domain:** Autonomous Software Development Loop & Agent State Machine  

---

## 1. Business Logic Architecture

The core value proposition of the system is autonomous software feature creation, bug fixing, and testing through an agentic pipeline.

### The 8-Stage Agent State Machine (`AgentStateMachine`)
1. **RECEIVED:** Session initialized with prompt requirement.
2. **ANALYZING:** Requirement & workspace structure analyzed via `RequirementAndProjectAnalyzer`.
3. **PLANNING:** Implementation plan generated via `PlanningAgent`.
4. **AWAITING_APPROVAL:** Execution pauses if `auto_approve=False` for user review.
5. **IMPLEMENTING:** `CodingAgent` executes 7-step safe modification protocol.
6. **TESTING:** `TestingValidationAgent` runs targeted test runner.
7. **DEBUGGING:** If tests fail, `DebuggingAgent` performs root-cause analysis & patch repair.
8. **REVIEWING / COMPLETED / FAILED:** Code reviewer checks final diffs and logs execution summary.

---

## 2. Business Logic Test Matrix & Failure Analysis

| Business Rule / Constraint | Enforced In | Audit Result | Severity |
| :--- | :--- | :--- | :---: |
| **Execution Time Cap** | `AgentLimits.max_execution_time` (120s) | Enforced | Low |
| **Max Agent Iterations** | `AgentLimits.max_iterations` (20) | Enforced | Medium |
| **Max Tool Calls** | `AgentLimits.max_tool_calls` (50) | Enforced | Medium |
| **Max Files Changed** | `AgentLimits.max_files_changed` (10) | Enforced | Medium |
| **Infinite Debug Loop Guard**| `DebuggingAgent.failure_fingerprints` (3 loops) | Enforced | High |
| **7-Step Safe File Mod** | `CodingAgent.modify_file_safely` | Enforced | High |
| **Accidental File Deletion Guard**| `CodingSafeguardManager.check_deletion_safeguard` | Enforced (`.git`, `Dockerfile`, `package.json` protected) | High |
| **State Machine DB Persistence**| `sessions.py` API endpoint | **BROKEN (P0)** — `repository=None` passed to state machine | Critical |

---

## 3. Critical Business Logic Finding: Database Detachment

In `app/api/v1/endpoints/sessions.py`:
```python
# SESSIONS_DB: Dict[str, AgentSession] = {} is used in memory!
# State Machine launched without AgentRepository:
state_machine = AgentStateMachine(
    session=session,
    provider=provider,
    sandbox=SANDBOX_ADAPTER,
    sandbox_id=sandbox_id
    # repository=AgentRepository(db) is MISSING!
)
```
* **Impact:** 
  1. If the FastAPI process restarts or crashes, all session data and history are permanently lost.
  2. None of the agent steps, tool calls, code diffs, or test results are saved to PostgreSQL tables (`agent_runs`, `agent_steps`, `tool_calls`, `code_versions`).
  3. Frontends or external analytics tools querying the database for agent metrics will see 0 runs.
