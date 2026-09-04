from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class GitState(BaseModel):
    """Snapshot of current repository Git state."""
    commit_hash: str = Field(default="", description="Current HEAD commit SHA hash")
    branch_name: str = Field(default="main", description="Active branch name")
    is_dirty: bool = Field(default=False, description="True if there are uncommitted changes")
    staged_files: List[str] = Field(default_factory=list, description="Files staged for commit")
    unstaged_files: List[str] = Field(default_factory=list, description="Modified but unstaged files")
    untracked_files: List[str] = Field(default_factory=list, description="New untracked files")
    ahead_behind: Dict[str, int] = Field(
        default_factory=lambda: {"ahead": 0, "behind": 0},
        description="Commits ahead/behind remote"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GitStatusResult(BaseModel):
    """Result of git status invocation."""
    state: GitState
    raw_status: str = Field(default="", description="Raw stdout output from git status")
    success: bool = True
    error_message: Optional[str] = None


class FileDiffStat(BaseModel):
    """Statistics for a single file in a diff."""
    file_path: str
    additions: int = 0
    deletions: int = 0
    binary: bool = False


class GitDiffResult(BaseModel):
    """Result of git diff calculation."""
    diff_text: str = Field(default="", description="Unified diff text output")
    files_changed: List[str] = Field(default_factory=list, description="List of modified file paths")
    file_stats: List[FileDiffStat] = Field(default_factory=list, description="Per-file line addition/deletion metrics")
    total_additions: int = 0
    total_deletions: int = 0
    target_branch_or_commit: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class GitBranchResult(BaseModel):
    """Result of branch creation/checkout operation."""
    branch_name: str
    created: bool = False
    checked_out: bool = False
    previous_branch: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class GitCommitMetadata(BaseModel):
    """Metadata for a Git commit."""
    commit_hash: str
    branch_name: str
    message: str
    author_name: str
    author_email: str
    files_changed: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_id: Optional[str] = None
    run_id: Optional[str] = None


class GitCommitResult(BaseModel):
    """Result of commit creation operation."""
    commit_metadata: Optional[GitCommitMetadata] = None
    success: bool = True
    error_message: Optional[str] = None


class GitPushResult(BaseModel):
    """Result of push operation attempt."""
    remote: str
    branch_name: str
    pushed: bool = False
    authorized: bool = False
    output: str = ""
    error_message: Optional[str] = None


class GitAuditRecord(BaseModel):
    """Audit log entry for Git operations."""
    id: str
    task_id: str
    run_id: Optional[str] = None
    operation: str
    branch_name: str
    command: str
    exit_code: int
    output_summary: str
    protected_branch_checked: bool = True
    user_authorized: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Domain Exception Definitions
class ProtectedBranchError(Exception):
    """Raised when an action attempts to directly modify or checkout a protected branch."""
    def __init__(self, branch_name: str, action: str):
        self.branch_name = branch_name
        self.action = action
        super().__init__(
            f"Protected Branch Violation: Direct {action} on protected branch '{branch_name}' is forbidden. "
            "Autonomous tasks must execute on isolated feature branches."
        )


class UnauthorizedPushError(Exception):
    """Raised when git push is attempted without explicit user authorization."""
    def __init__(self, branch_name: str, remote: str):
        self.branch_name = branch_name
        self.remote = remote
        super().__init__(
            f"Unauthorized Push Blocked: Pushing branch '{branch_name}' to remote '{remote}' requires "
            "explicit user authorization (confirm_push=True). Automatic remote push is disabled."
        )


class GitOperationError(Exception):
    """Generic error encountered during Git operation."""
    pass
