"""Tool tests: the controlled tool layer contract.

These run the real ``ControlledToolLayer``, the real ``ToolRegistry`` and the
real tool implementations against a sandbox that does real filesystem work.
Nothing about validation, permissions, limits or auditing is mocked.
"""

import asyncio

import pytest

from app.core.exceptions import LimitExceededError, ToolExecutionError
from app.domain.entities.agent import AgentLimits
from app.domain.entities.tool import ToolExecutionStatus, ToolPermission
from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer
from app.infrastructure.tools.registry import ToolRegistry

from tests.support.factories import PASSING_PROJECT, make_run
from tests.support.sandboxes import FailingSandbox, HangingSandbox

pytestmark = [pytest.mark.tools, pytest.mark.integration]


# ------------------------------------------------------------------- registry
class TestToolRegistry:
    def test_every_documented_tool_is_registered(self):
        names = {t.name for t in ToolRegistry().get_all_tools()}
        assert names == {
            "list_files",
            "read_file",
            "write_file",
            "create_file",
            "delete_file",
            "search_files",
            "get_project_structure",
            "execute_command",
            "run_command",
            "run_tests",
            "get_git_status",
            "get_git_diff",
            "create_git_branch",
            "create_git_commit",
            "push_git_branch",
        }

    def test_unknown_tool_is_rejected(self):
        with pytest.raises(ToolExecutionError, match="Unknown tool"):
            ToolRegistry().get_tool("exfiltrate_secrets")

    def test_schemas_are_llm_ready(self):
        for schema in ToolRegistry().get_openai_schemas():
            assert schema["type"] == "function"
            assert schema["function"]["name"]
            assert schema["function"]["description"]
            assert schema["function"]["parameters"]["type"] == "object"

    def test_mutating_tools_require_more_than_read_permission(self):
        registry = ToolRegistry()
        for name in ("write_file", "create_file", "delete_file"):
            assert registry.get_tool(name).permission_required is ToolPermission.WRITE
        for name in ("execute_command", "run_tests", "push_git_branch"):
            assert registry.get_tool(name).permission_required is ToolPermission.EXECUTE


# ----------------------------------------------------------- happy-path tools
class TestFileToolsAgainstRealFilesystem:
    @pytest.mark.asyncio
    async def test_write_then_read_round_trip(self, sandbox, agent_run, tool_layer):
        sb, sandbox_id = sandbox

        write = await tool_layer.execute_tool(
            sandbox=sb,
            sandbox_id=sandbox_id,
            tool_name="write_file",
            args={"file_path": "src/module.py", "content": "VALUE = 42\n"},
            run=agent_run,
        )
        assert write.success, write.error

        read = await tool_layer.execute_tool(
            sandbox=sb,
            sandbox_id=sandbox_id,
            tool_name="read_file",
            args={"file_path": "src/module.py"},
            run=agent_run,
        )
        assert read.success
        assert read.output == "VALUE = 42\n"

    @pytest.mark.asyncio
    async def test_read_file_line_slice(self, sandbox, agent_run, tool_layer):
        sb, sandbox_id = sandbox
        await sb.write_file(sandbox_id, "lines.txt", "one\ntwo\nthree\nfour\n")

        result = await tool_layer.execute_tool(
            sandbox=sb,
            sandbox_id=sandbox_id,
            tool_name="read_file",
            args={"file_path": "lines.txt", "start_line": 2, "end_line": 3},
            run=agent_run,
        )
        assert result.output == "two\nthree"

    @pytest.mark.asyncio
    async def test_create_file_refuses_to_clobber(self, sandbox, agent_run, tool_layer):
        sb, sandbox_id = sandbox
        first = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="create_file",
            args={"file_path": "once.txt", "initial_content": "original"}, run=agent_run,
        )
        assert first.success

        second = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="create_file",
            args={"file_path": "once.txt", "initial_content": "overwrite"}, run=agent_run,
        )
        assert second.success is False
        assert "already exists" in (second.error or "")
        assert await sb.read_file(sandbox_id, "once.txt") == "original"

    @pytest.mark.asyncio
    async def test_delete_file_removes_it_from_disk(self, sandbox, agent_run, tool_layer):
        sb, sandbox_id = sandbox
        await sb.write_file(sandbox_id, "trash.txt", "junk")

        result = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="delete_file",
            args={"file_path": "trash.txt"}, run=agent_run,
        )
        assert result.success
        with pytest.raises(Exception):
            await sb.read_file(sandbox_id, "trash.txt")

    @pytest.mark.asyncio
    async def test_read_missing_file_fails_without_crashing(self, sandbox, agent_run, tool_layer):
        sb, sandbox_id = sandbox
        result = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": "nope.txt"}, run=agent_run,
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_list_files_enumerates_the_project(self, project_sandbox, agent_run, tool_layer):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        result = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="list_files",
            args={"directory_path": "."}, run=agent_run,
        )
        assert result.success
        assert "calculator.py" in result.output

    @pytest.mark.asyncio
    async def test_search_files_finds_matches_with_locations(self, project_sandbox, agent_run, tool_layer):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        result = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="search_files",
            args={"query": "def divide", "file_pattern": "*.py"}, run=agent_run,
        )
        assert result.success
        assert "calculator.py" in result.output

    @pytest.mark.asyncio
    async def test_search_files_reports_no_matches_cleanly(self, project_sandbox, agent_run, tool_layer):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        result = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="search_files",
            args={"query": "this_string_does_not_exist_anywhere", "file_pattern": "*.py"}, run=agent_run,
        )
        assert result.success is True  # exit code 1 from grep is "no match", not an error
        assert "No matches found" in result.output

    @pytest.mark.asyncio
    async def test_project_structure_falls_back_when_tree_is_absent(self, project_sandbox, agent_run, tool_layer):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        result = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="get_project_structure",
            args={"max_depth": 3}, run=agent_run,
        )
        assert result.success
        assert any(cmd.startswith("tree ") for cmd in sb.commands), "tree should be attempted first"
        assert any(cmd.startswith("find ") for cmd in sb.commands), "find fallback should be used"


# ----------------------------------------------------- validation and limits
class TestToolLayerGuards:
    @pytest.mark.asyncio
    async def test_unknown_tool_is_rejected_before_execution(self, sandbox, agent_run, tool_layer):
        sb, sandbox_id = sandbox
        with pytest.raises(ToolExecutionError, match="Unknown tool"):
            await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="rm_rf_everything", args={}, run=agent_run,
            )

    @pytest.mark.asyncio
    async def test_schema_violation_is_rejected(self, sandbox, agent_run, tool_layer):
        sb, sandbox_id = sandbox
        with pytest.raises(ToolExecutionError, match="schema validation failed"):
            await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
                args={"file_path": "a.txt"},  # missing required `content`
                run=agent_run,
            )

    @pytest.mark.asyncio
    async def test_out_of_range_argument_is_rejected(self, sandbox, agent_run, tool_layer):
        sb, sandbox_id = sandbox
        with pytest.raises(ToolExecutionError):
            await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="get_project_structure",
                args={"max_depth": 9999}, run=agent_run,
            )

    @pytest.mark.asyncio
    async def test_tool_call_budget_is_enforced(self, sandbox, tool_layer):
        sb, sandbox_id = sandbox
        run = make_run(limits=AgentLimits(max_tool_calls=2))

        for index in range(2):
            await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
                args={"file_path": f"f{index}.txt", "content": "x"}, run=run,
            )

        with pytest.raises(LimitExceededError, match="Maximum tool calls"):
            await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
                args={"file_path": "f2.txt", "content": "x"}, run=run,
            )

    @pytest.mark.asyncio
    async def test_files_changed_budget_is_enforced(self, sandbox, tool_layer):
        sb, sandbox_id = sandbox
        run = make_run(limits=AgentLimits(max_files_changed=2, max_tool_calls=99))

        for index in range(2):
            result = await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
                args={"file_path": f"changed{index}.py", "content": "x"}, run=run,
            )
            assert result.success

        blocked = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
            args={"file_path": "changed2.py", "content": "x"}, run=run,
        )
        assert blocked.success is False
        assert "Maximum files changed" in (blocked.error or "")
        # The write must not have happened.
        with pytest.raises(Exception):
            await sb.read_file(sandbox_id, "changed2.py")

    @pytest.mark.asyncio
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="LIMIT-01: LimitExceededError raised inside execute_tool's try block is swallowed by "
        "the generic `except Exception` handler and returned as an ordinary failed ToolResult with "
        "status FAILED. A budget breach is indistinguishable from a transient tool error, so the "
        "agent loop retries instead of aborting the run.",
    )
    async def test_limit_breach_is_distinguishable_from_a_tool_failure(self, sandbox, tool_layer):
        sb, sandbox_id = sandbox
        run = make_run(limits=AgentLimits(max_files_changed=1, max_tool_calls=99))
        await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
            args={"file_path": "first.py", "content": "x"}, run=run,
        )
        with pytest.raises(LimitExceededError):
            await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
                args={"file_path": "second.py", "content": "x"}, run=run,
            )

    @pytest.mark.asyncio
    async def test_rewriting_the_same_file_does_not_consume_the_budget(self, sandbox, tool_layer):
        sb, sandbox_id = sandbox
        run = make_run(limits=AgentLimits(max_files_changed=1, max_tool_calls=99))

        for _ in range(3):
            result = await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
                args={"file_path": "same.py", "content": "x"}, run=run,
            )
            assert result.success
        assert run.files_changed_count == 1

    @pytest.mark.asyncio
    async def test_output_is_capped_at_the_configured_limit(self, sandbox, tool_layer):
        sb, sandbox_id = sandbox
        run = make_run(limits=AgentLimits(max_generated_output=500))
        await sb.write_file(sandbox_id, "big.txt", "A" * 10_000)

        result = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": "big.txt"}, run=run,
        )
        assert "Output truncated" in result.output
        assert len(result.output) < 10_000

    @pytest.mark.asyncio
    async def test_slow_tool_is_timed_out_and_recorded(self, agent_run, tool_layer):
        sb = HangingSandbox(delay_seconds=30)
        sandbox_id = await sb.create_sandbox("timeout-session")
        tool = tool_layer.registry.get_tool("list_files")
        original = tool.timeout_seconds
        tool.timeout_seconds = 1
        try:
            result = await tool_layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="list_files",
                args={"directory_path": "."}, run=agent_run,
            )
        finally:
            tool.timeout_seconds = original

        assert result.success is False
        assert result.exit_code == 124
        assert "timed out" in (result.error or "")
        assert tool_layer.audit_records[-1].status is ToolExecutionStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_sandbox_failure_is_surfaced_as_a_failed_tool_result(self, agent_run, tool_layer):
        sb = FailingSandbox()
        result = await tool_layer.execute_tool(
            sandbox=sb, sandbox_id="sb-dead", tool_name="read_file",
            args={"file_path": "app.py"}, run=agent_run,
        )
        assert result.success is False
        assert "daemon unreachable" in (result.error or "")
        assert tool_layer.audit_records[-1].status in (
            ToolExecutionStatus.FAILED,
            ToolExecutionStatus.DENIED,
        )


# ------------------------------------------------------------------- auditing
class TestToolAuditTrail:
    @pytest.mark.asyncio
    async def test_every_call_produces_one_audit_record(self, sandbox, agent_run):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()

        await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
            args={"file_path": "a.py", "content": "x"}, run=agent_run,
        )
        await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": "a.py"}, run=agent_run,
        )

        assert [r.tool_name for r in layer.audit_records] == ["write_file", "read_file"]
        assert all(r.status is ToolExecutionStatus.SUCCESS for r in layer.audit_records)
        assert all(r.execution_duration_ms >= 0 for r in layer.audit_records)

    @pytest.mark.asyncio
    async def test_audit_record_attributes_the_caller(self, sandbox, agent_run):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()

        await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": "missing.py"}, run=agent_run,
            user_id="user-42", project_id="project-7",
        )
        record = layer.audit_records[-1]
        assert record.user_id == "user-42"
        assert record.project_id == "project-7"
        assert record.agent_run_id == agent_run.id

    @pytest.mark.asyncio
    async def test_secrets_in_tool_arguments_are_masked_in_the_audit_record(self, sandbox, agent_run):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()

        await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
            args={"file_path": "config.py", "content": "x", "password": "hunter2", "api_key": "sk-live-123"},
            run=agent_run,
        )
        recorded = str(layer.audit_records[-1].input_metadata)
        assert "hunter2" not in recorded
        assert "sk-live-123" not in recorded

    @pytest.mark.asyncio
    async def test_denied_calls_are_recorded_as_denied(self, sandbox, agent_run):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()

        result = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": "../../../etc/passwd"}, run=agent_run,
        )
        assert result.success is False
        assert layer.audit_records[-1].status is ToolExecutionStatus.DENIED

    @pytest.mark.asyncio
    async def test_concurrent_calls_all_get_audited(self, sandbox, agent_run):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()
        agent_run.limits = AgentLimits(max_tool_calls=50, max_files_changed=50)

        await asyncio.gather(
            *[
                layer.execute_tool(
                    sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
                    args={"file_path": f"concurrent_{i}.py", "content": str(i)}, run=agent_run,
                )
                for i in range(5)
            ]
        )
        assert len(layer.audit_records) == 5
