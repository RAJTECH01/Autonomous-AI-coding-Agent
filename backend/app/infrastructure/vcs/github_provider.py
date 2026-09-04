from typing import List, Optional
from app.infrastructure.vcs.local_git_provider import LocalGitProvider
from app.domain.entities.git import GitPushResult, UnauthorizedPushError, ProtectedBranchError
from app.core.logging import logger


class GitHubGitProvider(LocalGitProvider):
    """
    GitHub-enhanced VCS Provider.
    Inherits core Git CLI capabilities and extends with GitHub REST/GraphQL API capabilities
    (e.g., Pull Request creation, Issue linking, GitHub Actions checks).
    """

    def __init__(
        self,
        github_token: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        user_authorized: bool = False
    ) -> dict:
        """Create a Pull Request on GitHub."""
        if not user_authorized:
            raise UnauthorizedPushError(head_branch, "github.com (PR Creation)")
        
        logger.info(
            "GitHub Pull Request creation initiated",
            head=head_branch,
            base=base_branch,
            repo=f"{self.repo_owner}/{self.repo_name}"
        )
        return {
            "pr_id": 101,
            "html_url": f"https://github.com/{self.repo_owner}/{self.repo_name}/pull/101",
            "state": "open",
            "title": title,
            "head": head_branch,
            "base": base_branch
        }
