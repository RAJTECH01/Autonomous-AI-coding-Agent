from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.infrastructure.tools.base import BaseTool, ToolResult
from app.domain.entities.tool import ToolPermission
from app.domain.interfaces.sandbox import SandboxInterface


# 8. execute_command (and alias RunCommandTool)
class ExecuteCommandInput(BaseModel):
    command: str = Field(description="Shell command line string to execute")
    timeout_seconds: int = Field(default=60, ge=1, le=300, description="Maximum execution duration in seconds")


class ExecuteCommandOutput(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class ExecuteCommandTool(BaseTool):
    name = "execute_command"
    description = "Execute shell command inside workspace sandbox environment"
    args_schema = ExecuteCommandInput
    permission_required = ToolPermission.EXECUTE
    timeout_seconds = 120
    output_schema = ExecuteCommandOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: ExecuteCommandInput = self.validate_inputs(kwargs)  # type: ignore

        try:
            res = await sandbox.execute_command(
                sandbox_id,
                validated.command,
                timeout_seconds=validated.timeout_seconds,
            )
            return ToolResult(
                tool_name=self.name,
                success=res.exit_code == 0,
                output=res.stdout,
                error=res.stderr if res.exit_code != 0 else None,
                metadata={
                    "command": validated.command,
                    "exit_code": res.exit_code,
                    "duration_ms": res.duration_ms,
                },
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


class RunCommandTool(ExecuteCommandTool):
    """Backwards compatibility alias for execute_command tool."""
    name = "run_command"


# 9. run_tests
class RunTestsInput(BaseModel):
    test_path: Optional[str] = Field(default=None, description="Optional path to specific test file or directory")
    args: Optional[List[str]] = Field(default=None, description="Optional extra arguments to pass to pytest")


class RunTestsOutput(BaseModel):
    passed: bool
    exit_code: int
    summary: str


class RunTestsTool(BaseTool):
    name = "run_tests"
    description = "Run automated test suite (pytest/jest/junit) with targeted-first execution and framework output parsing"
    args_schema = RunTestsInput
    permission_required = ToolPermission.EXECUTE
    timeout_seconds = 120
    output_schema = RunTestsOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: RunTestsInput = self.validate_inputs(kwargs)  # type: ignore

        try:
            from app.application.agent.subagents.tester import TestingValidationAgent
            tester = TestingValidationAgent(sandbox=sandbox, sandbox_id=sandbox_id)

            test_result = await tester.run_testing_pipeline(custom_test_path=validated.test_path)

            return ToolResult(
                tool_name=self.name,
                success=test_result.passed,
                output=test_result.summary + "\n\n" + test_result.stdout,
                error=test_result.stderr if not test_result.passed else None,
                metadata=test_result.to_dict(),
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 10. get_git_status
class GetGitStatusInput(BaseModel):
    include_diff: bool = Field(default=False, description="Whether to include git diff output in status response")


class GetGitStatusOutput(BaseModel):
    branch: str
    modified_files: List[str]
    clean: bool


class GetGitStatusTool(BaseTool):
    name = "get_git_status"
    description = "Retrieve current git working tree status and modified files"
    args_schema = GetGitStatusInput
    permission_required = ToolPermission.READ
    timeout_seconds = 30
    output_schema = GetGitStatusOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: GetGitStatusInput = self.validate_inputs(kwargs)  # type: ignore

        try:
            status_res = await sandbox.execute_command(sandbox_id, "git status --porcelain -b", timeout_seconds=15)
            lines = [line.strip() for line in status_res.stdout.splitlines() if line.strip()]

            branch = "unknown"
            modified_files = []

            for line in lines:
                if line.startswith("##"):
                    branch = line.replace("##", "").strip()
                else:
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        modified_files.append(parts[1])

            output_str = f"Branch: {branch}\nModified files ({len(modified_files)}):\n" + "\n".join(modified_files)

            if validated.include_diff:
                diff_res = await sandbox.execute_command(sandbox_id, "git diff --stat", timeout_seconds=15)
                output_str += f"\n\nDiff Summary:\n{diff_res.stdout}"

            return ToolResult(
                tool_name=self.name,
                success=status_res.exit_code == 0,
                output=output_str,
                error=status_res.stderr if status_res.exit_code != 0 else None,
                metadata={
                    "branch": branch,
                    "modified_count": len(modified_files),
                    "clean": len(modified_files) == 0,
                },
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 11. get_git_diff
class GetGitDiffInput(BaseModel):
    target: Optional[str] = Field(default=None, description="Optional target commit or branch to diff against")
    cached: bool = Field(default=False, description="True to view staged diff (--cached)")


class GetGitDiffTool(BaseTool):
    name = "get_git_diff"
    description = "Retrieve git diff output showing file modifications and line changes"
    args_schema = GetGitDiffInput
    permission_required = ToolPermission.READ
    timeout_seconds = 30

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: GetGitDiffInput = self.validate_inputs(kwargs)  # type: ignore
        from app.infrastructure.vcs.local_git_provider import LocalGitProvider

        try:
            git_provider = LocalGitProvider(sandbox=sandbox, sandbox_id=sandbox_id)
            diff_res = await git_provider.get_diff(workspace_path="", target=validated.target, cached=validated.cached)

            return ToolResult(
                tool_name=self.name,
                success=diff_res.success,
                output=diff_res.diff_text or "No modifications detected in working tree.",
                error=diff_res.error_message,
                metadata={
                    "files_changed": diff_res.files_changed,
                    "total_additions": diff_res.total_additions,
                    "total_deletions": diff_res.total_deletions,
                },
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 12. create_git_branch
class CreateGitBranchInput(BaseModel):
    branch_name: str = Field(description="Name of new isolated branch to create")
    checkout: bool = Field(default=True, description="Whether to immediately check out the branch")


class CreateGitBranchTool(BaseTool):
    name = "create_git_branch"
    description = "Create an isolated Git branch for task execution. Rejects protected branch targets."
    args_schema = CreateGitBranchInput
    permission_required = ToolPermission.WRITE
    timeout_seconds = 30

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: CreateGitBranchInput = self.validate_inputs(kwargs)  # type: ignore
        from app.infrastructure.vcs.local_git_provider import LocalGitProvider

        try:
            git_provider = LocalGitProvider(sandbox=sandbox, sandbox_id=sandbox_id)
            branch_res = await git_provider.create_branch(
                workspace_path="", branch_name=validated.branch_name, checkout=validated.checkout
            )

            return ToolResult(
                tool_name=self.name,
                success=branch_res.success,
                output=f"Successfully created branch '{validated.branch_name}' (Checked out: {validated.checkout})",
                error=branch_res.error_message,
                metadata={"branch_name": branch_res.branch_name, "created": branch_res.created},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 13. create_git_commit
class CreateGitCommitInput(BaseModel):
    message: str = Field(description="Commit message describing software modifications")
    files: Optional[List[str]] = Field(default=None, description="Optional list of specific files to stage and commit")
    author_name: str = Field(default="Autonomous Agent", description="Git author name")
    author_email: str = Field(default="agent@autonomous.local", description="Git author email")


class CreateGitCommitTool(BaseTool):
    name = "create_git_commit"
    description = "Stage files and create a Git commit with metadata tracking. Rejects commits on protected branches."
    args_schema = CreateGitCommitInput
    permission_required = ToolPermission.WRITE
    timeout_seconds = 30

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: CreateGitCommitInput = self.validate_inputs(kwargs)  # type: ignore
        from app.infrastructure.vcs.local_git_provider import LocalGitProvider

        try:
            git_provider = LocalGitProvider(sandbox=sandbox, sandbox_id=sandbox_id)
            commit_res = await git_provider.create_commit(
                workspace_path="",
                message=validated.message,
                author_name=validated.author_name,
                author_email=validated.author_email,
                files=validated.files,
            )

            if not commit_res.success or not commit_res.commit_metadata:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    output="",
                    error=commit_res.error_message or "Commit failed.",
                )

            meta = commit_res.commit_metadata
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"Commit created: [{meta.commit_hash[:7]}] {meta.message}",
                metadata={
                    "commit_hash": meta.commit_hash,
                    "branch": meta.branch_name,
                    "files_changed": meta.files_changed,
                    "author": f"{meta.author_name} <{meta.author_email}>",
                },
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 14. push_git_branch
class PushGitBranchInput(BaseModel):
    remote: str = Field(default="origin", description="Remote repository name")
    branch_name: Optional[str] = Field(default=None, description="Branch to push")
    confirm_push: bool = Field(default=False, description="EXPLICIT user authorization toggle. Push fails if False.")


class PushGitBranchTool(BaseTool):
    name = "push_git_branch"
    description = "Attempt pushing branch to remote. STRICTLY requires confirm_push=True explicit user authorization."
    args_schema = PushGitBranchInput
    permission_required = ToolPermission.EXECUTE
    timeout_seconds = 45

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: PushGitBranchInput = self.validate_inputs(kwargs)  # type: ignore
        from app.infrastructure.vcs.local_git_provider import LocalGitProvider

        try:
            git_provider = LocalGitProvider(sandbox=sandbox, sandbox_id=sandbox_id)
            push_res = await git_provider.push_branch(
                workspace_path="",
                remote=validated.remote,
                branch_name=validated.branch_name,
                user_authorized=validated.confirm_push,
            )

            return ToolResult(
                tool_name=self.name,
                success=push_res.pushed,
                output=f"Pushed branch '{push_res.branch_name}' to '{push_res.remote}'. Output: {push_res.output}",
                error=push_res.error_message,
                metadata={"remote": push_res.remote, "branch": push_res.branch_name, "pushed": push_res.pushed},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))

