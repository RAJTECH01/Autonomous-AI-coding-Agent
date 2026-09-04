"""Git operations, scoped to an authenticated agent session.

Two structural fixes live here (finding CMD-01 / AUTHZ-06):

* Every route requires an authenticated caller who owns the session.
* ``workspace_path`` is no longer a client parameter. It is derived from the
  session's sandbox, and all commands run **inside** that sandbox. The previous
  module-level ``LocalGitProvider()`` had no sandbox, which meant every route
  executed shell strings on the backend host - unauthenticated.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.endpoints.sessions import (
    SANDBOX_ADAPTER,
    _load_session_for_caller,
)
from app.domain.entities.git import ProtectedBranchError, UnauthorizedPushError
from app.infrastructure.vcs.local_git_provider import LocalGitProvider
from app.schemas.auth import UserResponse
from app.schemas.git import (
    GitAuditRecordSchema,
    GitBranchRequestSchema,
    GitBranchResponseSchema,
    GitCommitRequestSchema,
    GitCommitResponseSchema,
    GitDiffResponseSchema,
    GitPushRequestSchema,
    GitPushResponseSchema,
    GitStatusResponseSchema,
)

router = APIRouter(prefix="/git", tags=["Git & VCS"])

# One provider per session so the audit trail survives across requests. Entries
# live and die with the session they belong to.
_SESSION_PROVIDERS: Dict[str, LocalGitProvider] = {}


def _provider_for_session(session_id: str, current_user: UserResponse) -> LocalGitProvider:
    machine = _load_session_for_caller(session_id, current_user)
    provider = _SESSION_PROVIDERS.get(session_id)
    if provider is None or provider.sandbox_id != machine.sandbox_id:
        provider = LocalGitProvider(sandbox=SANDBOX_ADAPTER, sandbox_id=machine.sandbox_id)
        _SESSION_PROVIDERS[session_id] = provider
    return provider


@router.get("/status", response_model=GitStatusResponseSchema)
async def get_git_status(
    session_id: str = Query(description="Agent session whose workspace to inspect"),
    include_diff: bool = Query(default=False, description="Include git diff in status"),
    current_user: UserResponse = Depends(get_current_user),
):
    """Retrieve Git repository status, active branch, and modified/untracked files."""
    provider = _provider_for_session(session_id, current_user)
    try:
        return await provider.get_status("", include_diff=include_diff)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git status error: {str(e)}")


@router.get("/diff", response_model=GitDiffResponseSchema)
async def get_git_diff(
    session_id: str = Query(description="Agent session whose workspace to inspect"),
    target: Optional[str] = Query(default=None, description="Optional target commit or branch"),
    cached: bool = Query(default=False, description="True for staged diff"),
    current_user: UserResponse = Depends(get_current_user),
):
    """Retrieve Git unified diff output and line modification stats."""
    provider = _provider_for_session(session_id, current_user)
    try:
        return await provider.get_diff("", target=target, cached=cached)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git diff error: {str(e)}")


@router.post("/branch", response_model=GitBranchResponseSchema)
async def create_git_branch(
    body: GitBranchRequestSchema,
    session_id: str = Query(description="Agent session whose workspace to modify"),
    current_user: UserResponse = Depends(get_current_user),
):
    """Create an isolated feature branch. Prevents targetting protected branches."""
    provider = _provider_for_session(session_id, current_user)
    try:
        return await provider.create_branch("", branch_name=body.branch_name, checkout=body.checkout)
    except ProtectedBranchError as pbe:
        raise HTTPException(status_code=400, detail=str(pbe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Branch creation error: {str(e)}")


@router.post("/commit", response_model=GitCommitResponseSchema)
async def create_git_commit(
    body: GitCommitRequestSchema,
    session_id: str = Query(description="Agent session whose workspace to commit"),
    current_user: UserResponse = Depends(get_current_user),
):
    """Stage files and create a Git commit with metadata tracking."""
    provider = _provider_for_session(session_id, current_user)
    try:
        return await provider.create_commit(
            workspace_path="",
            message=body.message,
            author_name=body.author_name,
            author_email=body.author_email,
            files=body.files,
        )
    except ProtectedBranchError as pbe:
        raise HTTPException(status_code=400, detail=str(pbe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Commit error: {str(e)}")


@router.post("/push", response_model=GitPushResponseSchema)
async def push_git_branch(
    body: GitPushRequestSchema,
    session_id: str = Query(description="Agent session whose branch to push"),
    current_user: UserResponse = Depends(get_current_user),
):
    """Push a branch. Authorization comes from this authenticated request, not from
    the agent: the caller confirming the push is a human with a token."""
    provider = _provider_for_session(session_id, current_user)
    try:
        return await provider.push_branch(
            workspace_path="",
            remote=body.remote,
            branch_name=body.branch_name,
            user_authorized=body.confirm_push,
        )
    except UnauthorizedPushError as upe:
        raise HTTPException(status_code=403, detail=str(upe))
    except ProtectedBranchError as pbe:
        raise HTTPException(status_code=400, detail=str(pbe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Push error: {str(e)}")


@router.get("/audit-log", response_model=List[GitAuditRecordSchema])
async def get_git_audit_log(
    session_id: str = Query(description="Agent session whose Git audit trail to read"),
    task_id: Optional[str] = Query(default=None, description="Optional task ID filter"),
    current_user: UserResponse = Depends(get_current_user),
):
    """Fetch the auditable ledger of Git operations for one session."""
    provider = _provider_for_session(session_id, current_user)
    try:
        return await provider.get_audit_logs(task_id=task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit log query error: {str(e)}")
