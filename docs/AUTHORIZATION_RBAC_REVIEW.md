# Authorization / RBAC Review

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  
**Module:** `app/core/permissions.py` & Project Services  

---

## 1. Role & Permission Architecture

The application defines two levels of role-based access control (RBAC):

### System Level User Roles (`app/domain/entities/user.py`)
- `administrator` / `admin`: Full system-wide administrative access. Bypasses project-level restriction checks.
- `user`: Default registered account.

### Project Level Roles (`app/core/permissions.py`)
Role hierarchy and numerical levels:
- `owner` / `project owner` (Level 40): Full control, delete project, manage members.
- `maintainer` (Level 30): Modify project configuration, push code.
- `member` / `project member` (Level 20): Read/Write project files and launch tasks.
- `viewer` (Level 10): Read-only access to project files and session outputs.

---

## 2. RBAC Enforcement Audit

```python
# PermissionChecker implementation in app/core/permissions.py
class PermissionChecker:
    @staticmethod
    def check_project_access(user_id, user_role, project_owner_id, member_role, required_role):
        # 1. System administrators bypass project-level restriction
        if user_role in {"admin", "administrator"}: return
        # 2. Project owner always has full permission
        if str(user_id) == str(project_owner_id): return
        # 3. Check member role requirement against hierarchy
        user_level = PROJECT_ROLE_HIERARCHY.get(user_proj_role, 0)
        required_level = PROJECT_ROLE_HIERARCHY.get(required_role, 100)
        if user_level < required_level:
            raise AuthorizationError("Access denied: Requires privilege or higher.")
```

### Coverage Across Endpoints

| Resource | Action | Endpoint | Required Role | Enforcement Status |
| :--- | :--- | :--- | :--- | :---: |
| **Project** | Create | `POST /projects` | Authenticated `user` | Enforced |
| **Project** | List | `GET /projects` | Authenticated `user` | Enforced |
| **Project** | Read | `GET /projects/{id}` | `VIEWER` (Level 10) | Enforced |
| **Project** | Update | `PUT /projects/{id}` | `MAINTAINER` (Level 30) | Enforced |
| **Project** | Delete | `DELETE /projects/{id}` | `OWNER` (Level 40) | Enforced |
| **Agent Session** | Create | `POST /sessions` | NONE | **BYPASSED (P0)** |
| **Agent Session** | Read | `GET /sessions/{id}` | NONE | **BYPASSED (P0)** |

---

## 3. Findings & Required Fixes

1. **Critical Endpoint Security Vulnerability (P0):** The `/sessions` router omits project access and current user verification. Anyone with a valid or arbitrary `project_id` string can create agent runs.
2. **Fix Recommendation:** Integrate `check_project_access` into `sessions.py` before initializing an `AgentSession`.
