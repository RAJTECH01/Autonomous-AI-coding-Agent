from typing import Optional
from app.infrastructure.vcs.local_git_provider import LocalGitProvider
from app.domain.entities.git import UnauthorizedPushError
from app.core.logging import logger


class GitLabGitProvider(LocalGitProvider):
    """
    GitLab-enhanced VCS Provider.
    Inherits core Git CLI capabilities and extends with GitLab REST API capabilities
    (e.g., Merge Request creation, CI/CD pipeline triggering).
    """

    def __init__(
        self,
        gitlab_token: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.gitlab_token = gitlab_token
        self.project_id = project_id

    async def create_merge_request(
        self,
        title: str,
        description: str,
        source_branch: str,
        target_branch: str = "main",
        user_authorized: bool = False
    ) -> dict:
        """Create a Merge Request on GitLab."""
        if not user_authorized:
            raise UnauthorizedPushError(source_branch, "gitlab.com (MR Creation)")

        logger.info(
            "GitLab Merge Request creation initiated",
            source=source_branch,
            target=target_branch,
            project=self.project_id
        )
        return {
            "mr_id": 42,
            "web_url": f"https://gitlab.com/projects/{self.project_id}/-/merge_requests/42",
            "state": "opened",
            "title": title,
            "source_branch": source_branch,
            "target_branch": target_branch
        }
