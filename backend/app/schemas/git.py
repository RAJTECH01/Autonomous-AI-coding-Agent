from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class GitStateSchema(BaseModel):
    commit_hash: str
    branch_name: str
    is_dirty: bool
    staged_files: List[str] = Field(default_factory=list)
    unstaged_files: List[str] = Field(default_factory=list)
    untracked_files: List[str] = Field(default_factory=list)
    timestamp: datetime


class GitStatusResponseSchema(BaseModel):
    state: GitStateSchema
    raw_status: str
    success: bool
    error_message: Optional[str] = None


class FileDiffStatSchema(BaseModel):
    file_path: str
    additions: int = 0
    deletions: int = 0
    binary: bool = False


class GitDiffResponseSchema(BaseModel):
    diff_text: str
    files_changed: List[str] = Field(default_factory=list)
    file_stats: List[FileDiffStatSchema] = Field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    target: Optional[str] = None
    success: bool


class GitBranchRequestSchema(BaseModel):
    branch_name: str = Field(..., description="Target branch name to create")
    checkout: bool = Field(default=True, description="Whether to checkout branch upon creation")


class GitBranchResponseSchema(BaseModel):
    branch_name: str
    created: bool
    checked_out: bool
    previous_branch: Optional[str] = None
    success: bool
    error_message: Optional[str] = None


class GitCommitRequestSchema(BaseModel):
    message: str = Field(..., description="Commit message")
    files: Optional[List[str]] = Field(default=None, description="Optional specific files to stage and commit")
    author_name: str = Field(default="Autonomous Agent", description="Author name")
    author_email: str = Field(default="agent@autonomous.local", description="Author email")


class GitCommitMetadataSchema(BaseModel):
    commit_hash: str
    branch_name: str
    message: str
    author_name: str
    author_email: str
    files_changed: List[str] = Field(default_factory=list)
    timestamp: datetime


class GitCommitResponseSchema(BaseModel):
    commit: Optional[GitCommitMetadataSchema] = None
    success: bool
    error_message: Optional[str] = None


class GitPushRequestSchema(BaseModel):
    remote: str = Field(default="origin", description="Remote name")
    branch_name: Optional[str] = Field(default=None, description="Branch name")
    confirm_push: bool = Field(..., description="EXPLICIT user authorization confirmation toggle")


class GitPushResponseSchema(BaseModel):
    remote: str
    branch_name: str
    pushed: bool
    authorized: bool
    output: str
    error_message: Optional[str] = None


class GitAuditRecordSchema(BaseModel):
    id: str
    task_id: str
    run_id: Optional[str] = None
    operation: str
    branch_name: str
    command: str
    exit_code: int
    output_summary: str
    protected_branch_checked: bool
    user_authorized: bool
    timestamp: datetime
