# Performance Report

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  

---

## 1. Performance Bottlenecks & Resource Management

### In-Memory Memory Leaks (High Severity)
* **`RateLimiter` (`app/core/rate_limiter.py`):** Timestamps are appended to `self._records[key]`. When keys become inactive, their empty/old record entries remain in memory indefinitely.
* **`BruteForceProtectionService` (`app/services/brute_force_service.py`):** Failed attempt counters are keyed by IP/email in `self._attempts`. Entries are only deleted on successful login or explicit lockout expiry check, causing unbounded memory growth under continuous automated probe attacks.
* **`SESSIONS_DB` (`app/api/v1/endpoints/sessions.py`):** Active agent session objects (containing memory history, prompt logs, and execution summaries) are appended to a global Python dictionary `SESSIONS_DB` and never garbage-collected.

### Execution Latency & Concurrency
* **LLM Calls:** Synchronous wait on Anthropic/OpenAI API responses (~2-5 seconds per iteration).
* **Docker Container Execution:** Subprocess calls to Docker CLI / SDK take ~300-800ms per container creation.
* **Database Queries:** Queries use indexed columns (`email`, `slug`, `refresh_token_hash`, `project_id`). No N+1 queries detected in existing repository methods.

---

## 2. Recommended Performance Optimizations

1. **Redis Key Expiration for Rate Limiting:**
   Replace Python dictionaries with Redis `INCR` and `EXPIRE` commands to ensure automatic memory cleanup and distributed state sharing across web workers.
2. **PostgreSQL Session Storage:**
   Persist agent sessions in PostgreSQL and cache active state in Redis with a 24-hour TTL.
3. **Database Connection Pool Tuning:**
   Configure `pool_size=20`, `max_overflow=10`, `pool_recycle=1800` in `create_async_engine`.
