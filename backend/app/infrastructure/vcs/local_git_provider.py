import os
import asyncio
import shlex
import uuid
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.domain.interfaces.git_provider import GitProviderInterface
from app.domain.entities.git import (
    GitState,
    GitStatusResult,
    GitDiffResult,
    FileDiffStat,
    GitBranchResult,
    GitCommitResult,
    GitCommitMetadata,
    GitPushResult,
    GitAuditRecord,
    ProtectedBranchError,
    UnauthorizedPushError,
    GitOperationError,
)
from app.domain.interfaces.sandbox import SandboxInterface
from app.core.logging import logger

DEFAULT_PROTECTED_BRANCHES = {"main", "master", "production", "release", "staging", "dev"}

# git check-ref-format, tightened: letters, digits and . _ / - only, never leading '-'.
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
# Revisions additionally allow git's ancestry syntax (HEAD~1, HEAD^, a..b).
SAFE_REV = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/~^-]{0,254}$")
# Remotes are names configured in the repository, never URLs (findings CMD-01, SSRF-02).
SAFE_REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
# Refuse to run repository-supplied hooks on commit/checkout/push (finding REPO-03).
GIT = "git -c core.hooksPath=/dev/null"


def validate_ref(ref: str, kind: str = "branch") -> str:
    """Reject anything that is not a plain git ref name."""
    candidate = (ref or "").strip()
    if not SAFE_REF.match(candidate) or ".." in candidate or "@{" in candidate or candidate.endswith(".lock"):
        raise GitOperationError(
            f"Invalid {kind} name {ref!r}: only letters, digits, '.', '_', '/' and '-' are permitted."
        )
    return candidate


def validate_rev(rev: str) -> str:
    """Validate a revision expression (HEAD~1, a..b, tag^). Shell metacharacters out."""
    candidate = (rev or "").strip()
    if not SAFE_REV.match(candidate) or "@{" in candidate:
        raise GitOperationError(
            f"Invalid revision {rev!r}: only letters, digits and '. _ / - ~ ^' are permitted."
        )
    return candidate


def validate_remote(remote: str) -> str:
    """Accept a configured remote name; refuse URLs and anything shell-significant."""
    candidate = (remote or "").strip()
    if not SAFE_REMOTE.match(candidate):
        raise GitOperationError(
            f"Invalid remote {remote!r}: pass a remote name configured in the repository, not a URL."
        )
    return candidate


class LocalGitProvider(GitProviderInterface):
    """
    Local Git CLI implementation of GitProviderInterface.
    Executes Git CLI commands against local disk or inside a sandbox container.
    Enforces Protected Branch safeguards and Push Authorization guards.
    """

    def __init__(
        self,
        sandbox: Optional[SandboxInterface] = None,
        sandbox_id: Optional[str] = None,
        protected_branches: Optional[set] = None,
    ):
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id
        self.protected_branches = protected_branches or DEFAULT_PROTECTED_BRANCHES
        self._audit_records: List[GitAuditRecord] = []

    def is_protected_branch(self, branch_name: str) -> bool:
        """Check if target branch is in protected branches set."""
        if not branch_name:
            return False
        clean_name = branch_name.strip().lower()
        return clean_name in self.protected_branches

    async def _run_command(self, workspace_path: str, command_str: str) -> tuple[int, str, str]:
        """Execute a git command inside the sandbox.

        There is deliberately no host-execution branch. The previous fallback ran
        ``asyncio.create_subprocess_shell`` on the backend host whenever no sandbox
        was supplied, which is how the unauthenticated Git routes reached host
        command execution (finding CMD-01).
        """
        if not (self.sandbox and self.sandbox_id):
            raise GitOperationError(
                "Git operations require a sandbox. Direct host execution is not permitted."
            )

        command = (
            f"cd {shlex.quote(workspace_path)} && {command_str}" if workspace_path else command_str
        )
        res = await self.sandbox.execute_command(self.sandbox_id, command, timeout_seconds=30)
        return res.exit_code, res.stdout, res.stderr

    def _log_audit(
        self,
        task_id: str,
        operation: str,
        branch_name: str,
        command: str,
        exit_code: int,
        output_summary: str,
        run_id: Optional[str] = None,
        protected_branch_checked: bool = True,
        user_authorized: bool = True,
    ) -> GitAuditRecord:
        record = GitAuditRecord(
            id=str(uuid.uuid4()),
            task_id=task_id,
            run_id=run_id,
            operation=operation,
            branch_name=branch_name,
            command=command,
            exit_code=exit_code,
            output_summary=output_summary[:500],
            protected_branch_checked=protected_branch_checked,
            user_authorized=user_authorized,
            timestamp=datetime.now(timezone.utc),
        )
        self._audit_records.append(record)
        logger.info("Git operation executed", operation=operation, branch=branch_name, exit_code=exit_code)
        return record

    async def get_current_state(self, workspace_path: str) -> GitState:
        """Record and return current repository Git state."""
        # Query branch and commit
        code, out_branch, _ = await self._run_command(workspace_path, f"{GIT} rev-parse --abbrev-ref HEAD")
        branch_name = out_branch.strip() if code == 0 else "unknown"

        code, out_sha, _ = await self._run_command(workspace_path, f"{GIT} rev-parse HEAD")
        commit_hash = out_sha.strip() if code == 0 else ""

        # Query porcelain status
        code, out_porcelain, _ = await self._run_command(workspace_path, f"{GIT} status --porcelain")
        
        staged: List[str] = []
        unstaged: List[str] = []
        untracked: List[str] = []

        if code == 0 and out_porcelain:
            for line in out_porcelain.splitlines():
                if len(line) >= 3:
                    index_status = line[0]
                    work_status = line[1]
                    filename = line[3:].strip()
                    
                    if index_status in ["M", "A", "D", "R", "C"]:
                        staged.append(filename)
                    if work_status in ["M", "D"]:
                        unstaged.append(filename)
                    if index_status == "?" and work_status == "?":
                        untracked.append(filename)

        is_dirty = bool(staged or unstaged or untracked)

        return GitState(
            commit_hash=commit_hash,
            branch_name=branch_name,
            is_dirty=is_dirty,
            staged_files=staged,
            unstaged_files=unstaged,
            untracked_files=untracked,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_status(self, workspace_path: str, include_diff: bool = False) -> GitStatusResult:
        state = await self.get_current_state(workspace_path)
        code, raw_status, stderr = await self._run_command(workspace_path, f"{GIT} status")

        self._log_audit(
            task_id="status_query",
            operation="git_status",
            branch_name=state.branch_name,
            command=f"{GIT} status",
            exit_code=code,
            output_summary=raw_status or stderr
        )

        return GitStatusResult(
            state=state,
            raw_status=raw_status if code == 0 else stderr,
            success=(code == 0),
            error_message=stderr if code != 0 else None
        )

    async def get_diff(
        self, workspace_path: str, target: Optional[str] = None, cached: bool = False
    ) -> GitDiffResult:
        cmd = f"{GIT} diff"
        if cached:
            cmd += " --cached"
        if target:
            cmd += f" {shlex.quote(validate_rev(target))}"

        code, diff_text, stderr = await self._run_command(workspace_path, cmd)
        
        # Calculate stats
        code_stat, stat_text, _ = await self._run_command(workspace_path, f"{cmd} --numstat")
        file_stats: List[FileDiffStat] = []
        files_changed: List[str] = []
        tot_add = 0
        tot_del = 0

        if code_stat == 0 and stat_text:
            for line in stat_text.splitlines():
                parts = line.strip().split(maxsplit=2)
                if len(parts) == 3:
                    add_str, del_str, fpath = parts
                    is_binary = add_str == "-" or del_str == "-"
                    adds = 0 if is_binary else int(add_str)
                    dels = 0 if is_binary else int(del_str)
                    files_changed.append(fpath)
                    tot_add += adds
                    tot_del += dels
                    file_stats.append(FileDiffStat(file_path=fpath, additions=adds, deletions=dels, binary=is_binary))

        state = await self.get_current_state(workspace_path)
        self._log_audit(
            task_id="diff_query",
            operation="git_diff",
            branch_name=state.branch_name,
            command=cmd,
            exit_code=code,
            output_summary=f"Changed files: {len(files_changed)}, +{tot_add}/-{tot_del}"
        )

        return GitDiffResult(
            diff_text=diff_text,
            files_changed=files_changed,
            file_stats=file_stats,
            total_additions=tot_add,
            total_deletions=tot_del,
            target_branch_or_commit=target,
            success=(code == 0),
            error_message=stderr if code != 0 else None
        )

    async def create_branch(
        self, workspace_path: str, branch_name: str, checkout: bool = True
    ) -> GitBranchResult:
        """Create an isolated feature branch."""
        if self.is_protected_branch(branch_name):
            raise ProtectedBranchError(branch_name, action="branch creation/override")

        safe_branch = validate_ref(branch_name)
        state = await self.get_current_state(workspace_path)
        prev_branch = state.branch_name

        quoted = shlex.quote(safe_branch)
        cmd = f"{GIT} checkout -b {quoted}" if checkout else f"{GIT} branch {quoted}"
        code, stdout, stderr = await self._run_command(workspace_path, cmd)

        self._log_audit(
            task_id="branch_op",
            operation="create_branch",
            branch_name=branch_name,
            command=cmd,
            exit_code=code,
            output_summary=stdout or stderr
        )

        if code != 0:
            return GitBranchResult(
                branch_name=branch_name,
                created=False,
                checked_out=False,
                previous_branch=prev_branch,
                success=False,
                error_message=stderr or stdout
            )

        return GitBranchResult(
            branch_name=branch_name,
            created=True,
            checked_out=checkout,
            previous_branch=prev_branch,
            success=True
        )

    async def checkout_branch(self, workspace_path: str, branch_name: str) -> GitBranchResult:
        """Checkout an existing branch while enforcing protected branch check."""
        state = await self.get_current_state(workspace_path)
        prev_branch = state.branch_name

        cmd = f"{GIT} checkout {shlex.quote(validate_ref(branch_name))}"
        code, stdout, stderr = await self._run_command(workspace_path, cmd)

        self._log_audit(
            task_id="branch_op",
            operation="checkout_branch",
            branch_name=branch_name,
            command=cmd,
            exit_code=code,
            output_summary=stdout or stderr
        )

        return GitBranchResult(
            branch_name=branch_name,
            created=False,
            checked_out=(code == 0),
            previous_branch=prev_branch,
            success=(code == 0),
            error_message=stderr if code != 0 else None
        )

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
        """Stage files, check protected branch guard, and create commit."""
        state = await self.get_current_state(workspace_path)
        
        # Protected branch guard check
        if self.is_protected_branch(state.branch_name):
            raise ProtectedBranchError(state.branch_name, action="direct commit")

        # Stage files. Paths are quoted, and `--` stops a leading dash from being
        # parsed as an option.
        if files:
            files_str = " ".join(shlex.quote(f) for f in files)
            stage_cmd = f"{GIT} add -- {files_str}"
        else:
            stage_cmd = f"{GIT} add -A"

        code_stage, out_stage, err_stage = await self._run_command(workspace_path, stage_cmd)
        if code_stage != 0:
            return GitCommitResult(success=False, error_message=f"Failed to stage files: {err_stage}")

        # Commit. Every interpolated value is shell-quoted: escaping only the double
        # quote left $(...) and backticks live inside the double-quoted string, which
        # made the commit message a command-execution vector (finding CMD-01).
        commit_cmd = (
            f"{GIT} -c author.name={shlex.quote(author_name)}"
            f" -c author.email={shlex.quote(author_email)}"
            f" -c user.name={shlex.quote(author_name)}"
            f" -c user.email={shlex.quote(author_email)}"
            f" commit -m {shlex.quote(message)}"
        )
        code_commit, out_commit, err_commit = await self._run_command(workspace_path, commit_cmd)

        self._log_audit(
            task_id=task_id or "commit_op",
            run_id=run_id,
            operation="create_commit",
            branch_name=state.branch_name,
            command=commit_cmd,
            exit_code=code_commit,
            output_summary=out_commit or err_commit
        )

        if code_commit != 0:
            return GitCommitResult(success=False, error_message=err_commit or out_commit)

        # Get new commit hash & diff stats
        new_state = await self.get_current_state(workspace_path)
        diff_res = await self.get_diff(workspace_path, target="HEAD~1")

        metadata = GitCommitMetadata(
            commit_hash=new_state.commit_hash,
            branch_name=new_state.branch_name,
            message=message,
            author_name=author_name,
            author_email=author_email,
            files_changed=diff_res.files_changed or (files or []),
            task_id=task_id,
            run_id=run_id,
            timestamp=datetime.now(timezone.utc)
        )

        return GitCommitResult(commit_metadata=metadata, success=True)

    async def push_branch(
        self, workspace_path: str, remote: str = "origin", branch_name: Optional[str] = None, user_authorized: bool = False
    ) -> GitPushResult:
        """Push branch to remote, ONLY if user_authorized is True."""
        state = await self.get_current_state(workspace_path)
        target_branch = branch_name or state.branch_name

        # Push guard check
        if not user_authorized:
            self._log_audit(
                task_id="push_op",
                operation="git_push",
                branch_name=target_branch,
                command=f"git push {remote} {target_branch}",
                exit_code=1,
                output_summary="Push rejected: user_authorized=False",
                user_authorized=False
            )
            raise UnauthorizedPushError(branch_name=target_branch, remote=remote)

        if self.is_protected_branch(target_branch):
            raise ProtectedBranchError(target_branch, action="remote push")

        safe_remote = validate_remote(remote)
        cmd = f"{GIT} push {shlex.quote(safe_remote)} {shlex.quote(validate_ref(target_branch))}"
        code, stdout, stderr = await self._run_command(workspace_path, cmd)

        self._log_audit(
            task_id="push_op",
            operation="git_push",
            branch_name=target_branch,
            command=cmd,
            exit_code=code,
            output_summary=stdout or stderr,
            user_authorized=True
        )

        return GitPushResult(
            remote=remote,
            branch_name=target_branch,
            pushed=(code == 0),
            authorized=True,
            output=stdout or stderr,
            error_message=stderr if code != 0 else None
        )

    async def get_audit_logs(self, task_id: Optional[str] = None) -> List[GitAuditRecord]:
        if task_id:
            return [r for r in self._audit_records if r.task_id == task_id]
        return self._audit_records
