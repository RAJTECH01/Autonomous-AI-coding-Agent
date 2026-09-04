"""Security tests: command injection, tool injection and log injection.

Assertions are made on the exact command string the layer hands to ``sh -c``,
captured by a recording sandbox and re-parsed with POSIX shell rules
(``shlex``). If a payload becomes its own command segment, the quoting was
broken - that is the definition of shell injection, and it holds identically on
Linux and Windows.

Tests that assert the *secure* behaviour of a defect that is still present are
marked ``xfail(strict=True)``: they report XFAIL today and turn into failures the
moment the defect is fixed, which is the signal to delete the marker.
"""

import inspect

import pytest

from app.core.exceptions import ToolExecutionError
from app.infrastructure.tools.controlled_tool_layer import (
    BLOCKED_COMMAND_SUBSTRINGS,
    ControlledToolLayer,
)
from app.infrastructure.vcs.local_git_provider import LocalGitProvider

from tests.support.factories import make_run
from tests.support.shell import ShellSyntaxError, split_segments

pytestmark = [pytest.mark.security, pytest.mark.integration]

# A marker word that only ever becomes its own command if quoting was broken.
MARKER = "INJECTED"


def segments_of(command: str):
    try:
        return split_segments(command)
    except ShellSyntaxError:
        return [["<unbalanced-quoting>"]]


def assert_single_command(command: str, marker: str = MARKER) -> None:
    """The command string must be exactly one command, with no substitution."""
    segments = segments_of(command)
    assert len(segments) == 1, f"payload split into {len(segments)} commands: {segments}"
    assert not any(seg and seg[0] == marker for seg in segments)
    assert "$(" not in command, "command substitution survived into the shell string"
    assert "`" not in command, "backtick substitution survived into the shell string"


# ------------------------------------------------------- file tool injection
class TestFileToolCommandInjection:
    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-02: DeleteFileTool builds \"rm '{clean_path}'\" by interpolation and "
        "PathValidator permits the single-quote character, so a crafted path closes the quote and "
        "appends further commands.",
    )
    async def test_delete_file_path_cannot_break_out_of_quotes(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="delete_file",
            args={"file_path": f"notes.txt'; {MARKER}; '"}, run=make_run(),
        )
        assert_single_command(sb.last_command)

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-02: ListFilesTool interpolates the path into \"find '{path}'\" and, on the "
        "fallback branch, into an entirely unquoted \"ls {path}\".",
    )
    async def test_list_files_path_cannot_break_out_of_quotes(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="list_files",
            args={"directory_path": f"src'; {MARKER}; '"}, run=make_run(),
        )
        for command in sb.commands:
            assert_single_command(command)

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-02: CreateFileTool interpolates the path into \"test -f '{path}'\".",
    )
    async def test_create_file_existence_probe_cannot_be_hijacked(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="create_file",
            args={"file_path": f"new.txt'; {MARKER}; '", "initial_content": ""}, run=make_run(),
        )
        assert_single_command(sb.last_command)

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-03: SearchFilesTool escapes single quotes in `query` but not in `file_pattern`, "
        "which is interpolated straight into --include='{file_pattern}'.",
    )
    async def test_search_file_pattern_is_shell_quoted(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="search_files",
            args={"query": "password", "file_pattern": f"*.py'; {MARKER}; '"}, run=make_run(),
        )
        assert_single_command(sb.last_command)

    @pytest.mark.asyncio
    async def test_search_query_is_escaped_regression(self, recording_sandbox):
        """This one is handled today - lock it down so it stays handled."""
        sb, sandbox_id = recording_sandbox
        await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="search_files",
            args={"query": f"secret'; {MARKER}; '", "file_pattern": "*.py"}, run=make_run(),
        )
        assert_single_command(sb.last_command)

    @pytest.mark.asyncio
    async def test_project_structure_depth_is_a_bounded_integer_regression(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        with pytest.raises(ToolExecutionError):
            await ControlledToolLayer().execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="get_project_structure",
                args={"max_depth": "3; " + MARKER}, run=make_run(),
            )

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-04: list_files/read_file/search_files carry only ToolPermission.READ, yet each "
        "builds a shell string from unvalidated input, so a read-only principal reaches arbitrary "
        "command execution without ever calling execute_command.",
    )
    async def test_read_only_role_cannot_reach_command_execution(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        layer = ControlledToolLayer()

        result = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="list_files",
            args={"directory_path": f"src'; {MARKER}; '"}, run=make_run(), user_role="viewer",
        )
        assert result.success is False
        for command in sb.commands:
            assert_single_command(command)


# ------------------------------------------------------------- git injection
class TestGitCommandInjection:
    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-01: create_branch interpolates branch_name into 'git checkout -b \"{name}\"'. "
        "Double quotes do not stop $(...) or backticks, and no schema constrains the ref name.",
    )
    async def test_branch_name_cannot_carry_command_substitution(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        await provider.create_branch(workspace_path="", branch_name=f"feature-$({MARKER})")
        assert "$(" not in sb.last_command

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-01: create_commit escapes only the double-quote character in the message, so "
        "$(...) and backticks in a commit message execute before git is invoked.",
    )
    async def test_commit_message_cannot_carry_command_substitution(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        await provider.create_commit(workspace_path="", message=f"fix: $({MARKER})")
        commit_commands = [c for c in sb.commands if "commit -m" in c]
        assert commit_commands
        assert all("$(" not in command for command in commit_commands)

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-01/SSRF-02: push_branch interpolates the remote into 'git push \"{remote}\"' "
        "with no allowlist, so the remote is both an injection vector and an exfiltration target.",
    )
    async def test_push_remote_cannot_carry_command_substitution(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        await provider.push_branch(
            workspace_path="", remote=f"origin-$({MARKER})", branch_name="feature-x", user_authorized=True
        )
        push_commands = [c for c in sb.commands if c.startswith("git push")]
        assert push_commands
        assert all("$(" not in command for command in push_commands)

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-01: get_diff interpolates the diff target into 'git diff \"{target}\"'.",
    )
    async def test_diff_target_cannot_carry_command_substitution(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        await provider.get_diff(workspace_path="", target=f"HEAD~1 $({MARKER})")
        assert all("$(" not in command for command in sb.commands)

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-04: the sandbox branch prefixes 'cd '{workspace_path}' && ...', and the "
        "workspace path is a client-supplied query parameter on every /api/v1/git route.",
    )
    async def test_workspace_path_cannot_break_out_of_the_cd_prefix(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        await provider.get_status(workspace_path=f"/tmp'; {MARKER}; '")
        for command in sb.commands:
            assert_single_command(command)

    @pytest.mark.vuln
    def test_git_provider_never_executes_on_the_host(self):
        """CMD-01 root cause: without a sandbox the provider shells out on the host."""
        source = inspect.getsource(LocalGitProvider._run_command)
        assert "create_subprocess_shell" in source, "source changed - re-review this test"

        pytest.xfail(
            "CMD-01: LocalGitProvider._run_command falls back to "
            "asyncio.create_subprocess_shell on the backend host when no sandbox is supplied, "
            "and app/api/v1/endpoints/git.py constructs exactly that provider at module scope "
            "for a set of unauthenticated routes."
        )

    @pytest.mark.asyncio
    async def test_protected_branches_are_refused_regression(self, recording_sandbox):
        from app.domain.entities.git import ProtectedBranchError

        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        with pytest.raises(ProtectedBranchError):
            await provider.create_branch(workspace_path="", branch_name="main")

    @pytest.mark.asyncio
    async def test_push_without_authorization_is_refused_regression(self, recording_sandbox):
        from app.domain.entities.git import UnauthorizedPushError

        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        with pytest.raises(UnauthorizedPushError):
            await provider.push_branch(workspace_path="", remote="origin", branch_name="feature-x")
        assert not [c for c in sb.commands if c.startswith("git push")]


# --------------------------------------------------------- command allowlist
class TestDestructiveCommandPolicy:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("command", ["rm -rf /", "mkfs.ext4 /dev/sda1", "shutdown -h now", "dd if=/dev/zero of=/dev/sda"])
    async def test_listed_destructive_commands_are_blocked_regression(self, recording_sandbox, command):
        sb, sandbox_id = recording_sandbox
        result = await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="execute_command",
            args={"command": command}, run=make_run(), user_role="project_owner",
        )
        assert result.success is False
        assert "security violation" in (result.error or "").lower()
        assert sb.commands == [], "the command reached the sandbox anyway"

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "command",
        [
            "rm -fr /",                                   # flag order
            "rm  -rf  /",                                 # extra whitespace
            "rm --recursive --force /",                    # long options
            "find / -xdev -delete",                        # different tool
            "echo cm0gLXJmIC8= | base64 -d | sh",          # encoded
            "python -c \"import shutil; shutil.rmtree('/')\"",  # interpreter
        ],
    )
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-05: validate_command_safety is a literal substring blocklist. Every equivalent "
        "spelling of a destructive command passes, so the control provides no real containment.",
    )
    async def test_equivalent_destructive_commands_are_also_blocked(self, recording_sandbox, command):
        sb, sandbox_id = recording_sandbox
        result = await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="execute_command",
            args={"command": command}, run=make_run(), user_role="project_owner",
        )
        assert result.success is False
        assert "security violation" in (result.error or "").lower()

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-05: the policy should be an executable allowlist parsed with shlex, not a "
        "blocklist of dangerous strings.",
    )
    def test_command_policy_is_allowlist_based(self):
        source = inspect.getsource(ControlledToolLayer.validate_command_safety)
        assert "ALLOWED" in source.upper(), f"still blocklist-based: {len(BLOCKED_COMMAND_SUBSTRINGS)} patterns"

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="CMD-05/T2: validate_command_safety only inspects the execute_command and "
        "run_command tools. Commands assembled inside every other tool bypass the check entirely.",
    )
    async def test_command_safety_applies_to_commands_built_by_other_tools(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="delete_file",
            args={"file_path": "x'; rm -rf /; '"}, run=make_run(),
        )
        assert all("rm -rf /" not in command for command in sb.commands)


# ------------------------------------------------------------- tool injection
class TestToolInjection:
    @pytest.mark.asyncio
    async def test_unregistered_tool_is_refused_regression(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        with pytest.raises(ToolExecutionError, match="Unknown tool"):
            await ControlledToolLayer().execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="curl", args={}, run=make_run(),
            )

    @pytest.mark.asyncio
    async def test_tool_arguments_are_schema_validated_regression(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        with pytest.raises(ToolExecutionError, match="schema validation failed"):
            await ControlledToolLayer().execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="execute_command",
                args={"command": "echo hi", "timeout_seconds": 100_000}, run=make_run(),
            )

    @pytest.mark.asyncio
    async def test_tool_timeout_is_capped_regardless_of_request_regression(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        layer = ControlledToolLayer()
        source = inspect.getsource(layer.execute_tool)
        assert "min(tool.timeout_seconds, 120)" in source, "the hard timeout ceiling was removed"


# --------------------------------------------------------------- log injection
class TestLogInjection:
    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="LOG-01: newlines and control characters in attacker-controlled fields are written "
        "into audit records and log events verbatim, so forged log lines can be injected.",
    )
    async def test_newlines_in_a_tool_argument_do_not_reach_the_audit_record(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        layer = ControlledToolLayer()
        forged = 'x\n2026-01-01T00:00:00Z [info] risk_evaluation approved=true\n'

        await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": forged}, run=make_run(),
        )
        recorded = layer.audit_records[-1].input_metadata.get("file_path", "")
        assert "\n" not in recorded, "raw newline stored verbatim in the audit record"
        assert "\r" not in recorded

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="LOG-01: GitAuditRecord.command and output_summary store raw attacker text, and the "
        "git audit log is served unauthenticated at GET /api/v1/git/audit-log.",
    )
    async def test_git_audit_record_escapes_control_characters(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        await provider.create_branch(
            workspace_path="", branch_name="feature\n[info] approved_by=admin"
        )
        records = await provider.get_audit_logs()
        assert all("\n" not in (record.command or "") for record in records)
