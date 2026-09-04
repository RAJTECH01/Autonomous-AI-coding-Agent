# Input Validation Report

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  
**Scope:** REST API Request Schemas, Path Sanitization, Tool Arguments, Command Filtering.  

---

## 1. Input Validation Architecture

Input validation occurs across three distinct layers:
1. **API Schema Layer:** Pydantic v2 schemas (`UserCreate`, `ProjectCreate`, `CreateSessionRequest`) enforce type safety, regex constraints, and min/max lengths.
2. **Tool Execution Layer:** `ControlledToolLayer` validates JSON tool parameters against Pydantic definitions before tool invocation.
3. **Filesystem Security Layer:** `PathValidator` inspects all file path strings to ensure operations remain bounded within the sandbox root directory.

---

## 2. Attack Vector Validation Results

| Attack Type | Payload Tested | Result | Defense Mechanism |
| :--- | :--- | :---: | :--- |
| **SQL Injection** | `' OR 1=1 --`, `admin'; DROP TABLE users; --` | **BLOCKED** | SQLAlchemy async ORM parameterization |
| **Path Traversal** | `../../../../etc/passwd`, `C:\Windows\System32` | **BLOCKED** | `PathValidator.validate_workspace_path` |
| **Secret File Access** | `.env`, `id_rsa`, `server.key` | **BLOCKED** | `BLOCKED_SECRET_FILES` & extensions list |
| **Fork Bomb** | `:(){ :|:& };:` | **BLOCKED** | `BLOCKED_COMMAND_SUBSTRINGS` filtering |
| **Destructive Commands**| `rm -rf /`, `mkfs`, `dd if=/dev/zero` | **BLOCKED** | `validate_command_safety` in tool layer |
| **Payload Overflow** | 10MB prompt string | **TRUNCATED** | Tool output & memory token limits |
| **Malformed JSON** | `{"prompt": invalid_json` | **HTTP 422** | FastAPI / Pydantic JSON parser |

---

## 3. Tool Command Filtering (`app/infrastructure/tools/controlled_tool_layer.py`)

```python
BLOCKED_COMMAND_SUBSTRINGS = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",  # fork bomb
    "chmod 777 /",
    "shutdown",
    "reboot",
]
```

### Recommendation
While string filtering catches obvious destructive commands, running in a strictly unprivileged Docker container with `network_enabled=False` and non-root user provides true defense-in-depth against malicious command payloads.
