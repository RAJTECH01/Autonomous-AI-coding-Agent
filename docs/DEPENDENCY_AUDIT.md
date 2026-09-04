# Dependency Audit

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  

---

## 1. Backend Python Dependencies (`backend/requirements.txt`)

| Package | Specified Version | Status | Security / Vulnerability Check |
| :--- | :--- | :---: | :--- |
| `fastapi` | `>=0.110.0` | Up-to-Date | No known high vulnerabilities |
| `uvicorn[standard]` | `>=0.28.0` | Up-to-Date | Production ASGI server |
| `pydantic` | `>=2.6.0` | Up-to-Date | V2 type validation |
| `sqlalchemy[asyncio]` | `>=2.0.28` | Up-to-Date | Async ORM core |
| `asyncpg` | `>=0.29.0` | Up-to-Date | PostgreSQL driver |
| `alembic` | `>=1.13.1` | Up-to-Date | Schema migration tool |
| `redis` | `>=5.0.3` | Up-to-Date | Cache & broker client |
| `celery` | `>=5.3.6` | Installed | Unused in code (FastAPI `BackgroundTasks` used) |
| `python-jose[cryptography]` | `>=3.3.0` | Up-to-Date | JWT encoding/decoding |
| `passlib[bcrypt,argon2]` | `>=1.7.4` | Deprecation Warning | Warning on `argon2-cffi` version lookup (minor) |
| `argon2-cffi` | `>=23.1.0` | Up-to-Date | Primary password hasher |
| `docker` | `>=7.0.0` | Up-to-Date | Python Docker SDK |
| `structlog` | `>=24.1.0` | Up-to-Date | Structured JSON logger |
| `openai` / `anthropic` | `>=1.14.0` / `>=0.20.0` | Up-to-Date | AI SDKs |

---

## 2. Frontend Node.js Dependencies (`frontend/package.json`)

Execution of `npm audit` revealed 4 vulnerabilities:
- **Critical (1):** High severity nested dependency issue.
- **High (1):** Outdated transitive package.
- **Moderate (2):** Minor devDependency advisories.

### Direct Dependencies
- `react`: `^18.2.0`
- `react-dom`: `^18.2.0`
- `axios`: `^1.6.8`
- `zustand`: `^4.5.2`
- `lucide-react`: `^0.359.0`
- `typescript`: `^5.2.2` (devDependency)
- `vite`: `^5.1.6` (devDependency)

---

## 3. Recommendations
1. Run `npm audit fix` in `frontend` to patch vulnerable nested dependencies.
2. Either configure Celery tasks or remove `celery` from `requirements.txt` to keep dependencies clean.
