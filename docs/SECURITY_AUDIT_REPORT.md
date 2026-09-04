# Security Audit Report

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  
**Audit Scope:** Authentication, Authorization, Sandbox Isolation, Path Traversal, Secrets Management, Security Headers, and Rate Limiting.  

---

## 1. Executive Security Assessment

The platform demonstrates high security maturity in sandbox isolation and path security, but suffers from critical authentication omissions in agent API endpoints and in-memory rate-limiting vulnerabilities.

---

## 2. Vulnerability Findings Summary

| ID | Vulnerability Title | Severity | Location | Status |
| :--- | :--- | :---: | :--- | :---: |
| **SEC-01** | Unauthenticated Agent Session Creation Endpoint | **P0 (Critical)** | `app/api/v1/endpoints/sessions.py` | Confirmed |
| **SEC-02** | In-Memory Rate Limiter State (Non-Distributed & Leak) | **P1 (High)** | `app/core/rate_limiter.py` | Confirmed |
| **SEC-03** | In-Memory Brute Force Protection State | **P1 (High)** | `app/services/brute_force_service.py` | Confirmed |
| **SEC-04** | Secret Tokens / Credentials in HTTP Response Payload | **P2 (Medium)** | `app/services/auth_service.py` | Confirmed |
| **SEC-05** | Development Secret Key Hardcoded in Default Config | **P2 (Medium)** | `app/core/config.py` | Confirmed |
| **SEC-06** | CORS Wildcard Headers for Credentials | **P3 (Low)** | `app/main.py` | Confirmed |

---

## 3. Detailed Security Vulnerabilities

### SEC-01: Unauthenticated Agent Session Endpoint (P0 - Critical)
* **Description:** The `/api/v1/sessions` endpoint allows any unauthenticated HTTP client to trigger background agent execution loops and spin up Docker containers.
* **Code Evidence (`app/api/v1/endpoints/sessions.py`):**
  ```python
  @router.post("/sessions", response_model=SessionResponse)
  async def create_agent_session(req: CreateSessionRequest, background_tasks: BackgroundTasks):
      # Omitted: current_user: UserResponse = Depends(get_current_user)
      session = AgentSession(
          ...
          user_id="u-1001",  # Hardcoded anonymous user!
      )
  ```
* **Impact:** Unauthorized resource exhaustion, unauthenticated Docker container creation, potential denial of service (DoS), and arbitrary code execution inside sandbox.
* **Remediation:** Add `current_user: UserResponse = Depends(get_current_user)` dependency to all endpoints in `sessions.py` and bind `session.user_id = current_user.id`.

---

### SEC-02 & SEC-03: In-Memory Rate Limiting & Lockout Leaks (P1 - High)
* **Description:** `RateLimiter` (`_records`) and `BruteForceProtectionService` (`_attempts`) maintain attempt histories in standard Python dictionaries.
* **Impact:** 
  1. In multi-worker deployments (e.g., Uvicorn with 4 workers or multiple Kubernetes pods), rate limits are not shared across processes, allowing attackers to bypass rate limits by targeting different workers.
  2. Inactive keys are never purged from `_records`, leading to unbounded RAM consumption (memory leak).
* **Remediation:** Refactor `RateLimiter` and `BruteForceProtectionService` to store rate limits and attempt counters in Redis using key TTLs (`EXPIRE`).

---

### SEC-04: Password Reset Token Leak in API Response (P2 - Medium)
* **Description:** `request_password_reset` in `AuthService` returns `MessageResponse(message=..., token=opaque_token)`.
* **Impact:** Since an SMTP email sender is not integrated, the password reset token is returned directly in the REST response body. Anyone requesting a password reset for any user email can view the token and reset the user's password.
* **Remediation:** Remove `token` from `MessageResponse` payload and dispatch tokens exclusively via secure email transport.

---

## 4. Security Mechanisms Validated & Working

1. **Docker Sandbox Containment:** Containers are run with `Tail -f /dev/null`, memory cap (512MB), CPU quota (2.0), PID limit (100), read-only root filesystems where appropriate, and `network_enabled=False` by default.
2. **Path Traversal Security:** `PathValidator.validate_workspace_path` sanitizes all input paths, blocks `..` constructs, and rejects system files (`/etc`, `C:\Windows`) and secret files (`.env`, `.pem`, `id_rsa`).
3. **Command Execution Safety:** `ControlledToolLayer` screens commands for fork bombs (`:(){ :|:& };:`), `rm -rf /`, `mkfs`, `dd if=`, and `chmod 777 /`.
4. **Password Hashing:** Argon2id primary hashing (`passlib` + `argon2-cffi`) with fallback verification.
5. **Token Reuse Protection:** Refresh token rotation revokes all active auth sessions if an already-revoked refresh token is re-submitted.
