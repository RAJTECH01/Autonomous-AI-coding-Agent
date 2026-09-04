# Error Handling & Reliability Review

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  

---

## 1. Exception Hierarchy & Global Handlers

The application implements a centralized exception hierarchy inheriting from `DomainError`:
- `DomainError` (Base class)
  - `ConfigurationError`
  - `AuthenticationError` (Maps to HTTP 401)
  - `AuthorizationError` (Maps to HTTP 403)
  - `ResourceNotFoundError` (Maps to HTTP 404)
  - `ToolExecutionError` (Maps to HTTP 422)
  - `SandboxExecutionError` (Maps to HTTP 422)
  - `LimitExceededError` (Maps to HTTP 400)
  - `AgentLoopGuardrailError` (Maps to HTTP 400)

### Response Payload Uniformity
Centralized handlers in `app/core/exception_handlers.py` format error outputs cleanly with Correlation IDs:
```json
{
  "error": {
    "code": "ACCESS_DENIED",
    "message": "Access denied: Requires maintainer privilege or higher.",
    "correlation_id": "c-9283-4819"
  }
}
```

---

## 2. Reliability & Resilience Assessment

| Scenario | Handling Strategy | Audit Result |
| :--- | :--- | :---: |
| **Database Connection Failure** | Caught in `/readiness` check; returns `status: unhealthy` | Handled |
| **LLM Provider API Outage** | Caught in agent loop; marks session `status: FAILED` with error summary | Handled |
| **Sandbox Command Timeout** | `asyncio.wait_for` terminates process after timeout | Handled |
| **Infinite Debug Loops** | `failure_fingerprints` count halts execution after 3 loops | Handled |
| **Uncaught Server Exception** | `global_exception_handler` catches `Exception`, masks internals with HTTP 500 | Handled |
| **Process Restart During Run**| `SESSIONS_DB` in RAM causes complete state loss on crash | **VULNERABLE** |
