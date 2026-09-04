from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities.git import (
    GitState,
    GitStatusResult,
    GitDiffResult,
    GitBranchResult,
    GitCommitResult,
    GitCommitMetadata,
    GitPushResult,
    GitAuditRecord,
)


class GitProviderInterface(ABC):
    """
    Abstract interface for Version Control System (VCS) operations.
    Allows local Git CLI, GitHub REST/GraphQL API, and GitLab API providers
    to be swapped seamlessly behind a domain boundary.
    """

    @abstractmethod
    async def get_current_state(self, workspace_path: str) -> GitState:
        """Record and return the current repository Git state."""
        pass

    @abstractmethod
    async def get_status(self, workspace_path: str, include_diff: bool = False) -> GitStatusResult:
        """Query repository working tree status (`git status`)."""
        pass

    @abstractmethod
    async def get_diff(
        self, workspace_path: str, target: Optional[str] = None, cached: bool = False
    ) -> GitDiffResult:
        """Calculate and return repository diff (`git diff`)."""
        pass

    @abstractmethod
    async def create_branch(
        self, workspace_path: str, branch_name: str, checkout: bool = True
    ) -> GitBranchResult:
        """
        Create a new isolated task branch.
        Prevents creation/checkout targeting protected branches.
        """
        pass

    @abstractmethod
    async def checkout_branch(self, workspace_path: str, branch_name: str) -> GitBranchResult:
        """
        Switch active workspace branch.
        Prevents switching to protected branches for mutation.
        """
        pass

    @abstractmethod
    async def create_commit(
        self,
        workspace_path: str,
        message: str,
        author_name: str = "Autonomous Agent",
        author_email: str = "agent@autonomous.local",
        files: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> GitCommitResult:
        """
        Stage specified (or all) changes and create a Git commit.
        Stores commit metadata and enforces protected branch guards.
        """
        pass

    @abstractmethod
    async def push_branch(
        self, workspace_path: str, remote: str = "origin", branch_name: Optional[str] = None, user_authorized: bool = False
    ) -> GitPushResult:
        """
        Attempt pushing branch to remote repository.
        STRICTLY requires user_authorized=True. Never pushes automatically.
        """
        pass

    @abstractmethod
    def is_protected_branch(self, branch_name: str) -> bool:
        """Check if branch_name is in protected branch configuration list."""
        pass

    @abstractmethod
    async def get_audit_logs(self, task_id: Optional[str] = None) -> List[GitAuditRecord]:
        """Fetch auditable ledger of Git operations."""
        pass
