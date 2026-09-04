"""Failure, retry and degradation tests.

The interesting scenarios here are driven by *real* failing code: pytest actually
runs against a broken project inside the sandbox, so the classification of syntax
errors, runtime errors and assertion failures is verified against genuine
interpreter output rather than a canned string.
"""

import pytest

from app.application.agent.safeguards import CodingSafeguardManager
from app.application.agent.subagents.tester import TestingValidationAgent
from app.core.exceptions import SandboxExecutionError
from app.domain.entities.coding_agent import SafeguardViolationError
from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer

from tests.support.factories import (
    FAILING_PROJECT,
    PASSING_PROJECT,
    RUNTIME_ERROR_PROJECT,
    SYNTAX_ERROR_PROJECT,
    make_run,
)
from tests.support.sandboxes import FailingSandbox, FlakySandbox, HangingSandbox, InProcessSandbox

pytestmark = [pytest.mark.failure, pytest.mark.integration]


# ------------------------------------------------------------- real test runs
class TestRealTestExecution:
    @pytest.mark.asyncio
    async def test_a_healthy_project_passes(self, project_sandbox):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        result = await TestingValidationAgent(sandbox=sb, sandbox_id=sandbox_id).run_testing_pipeline()

        assert result.passed is True, result.summary
        assert result.total_tests >= 2
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_failing_tests_are_detected_and_located(self, project_sandbox):
        sb, sandbox_id = await project_sandbox(FAILING_PROJECT)
        result = await TestingValidationAgent(sandbox=sb, sandbox_id=sandbox_id).run_testing_pipeline()

        assert result.passed is False
        assert result.failed_count >= 1
        assert result.failing_tests
        assert any("test_add" in failing.test_name for failing in result.failing_tests)
        assert result.likely_causes

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="TEST-01: PytestAdapter._classify_likely_cause looks for the string 'AssertionError', "
        "but pytest's short summary renders assertion failures as 'assert -1 == 5'. Every assertion "
        "failure is therefore mislabelled 'Runtime Error: Unhandled exception', which is the root "
        "cause handed to the debugging agent.",
    )
    async def test_assertion_failures_are_classified_as_assertion_failures(self, project_sandbox):
        sb, sandbox_id = await project_sandbox(FAILING_PROJECT)
        result = await TestingValidationAgent(sandbox=sb, sandbox_id=sandbox_id).run_testing_pipeline()
        assert any("Assertion" in cause for cause in result.likely_causes), result.likely_causes

    @pytest.mark.asyncio
    async def test_generated_syntax_error_is_classified(self, project_sandbox):
        sb, sandbox_id = await project_sandbox(SYNTAX_ERROR_PROJECT)
        result = await TestingValidationAgent(sandbox=sb, sandbox_id=sandbox_id).run_testing_pipeline()

        assert result.passed is False
        combined = " ".join(result.likely_causes) + result.stdout + result.stderr
        assert "SyntaxError" in combined or "Syntax Error" in combined

    @pytest.mark.asyncio
    async def test_generated_runtime_error_is_classified(self, project_sandbox):
        sb, sandbox_id = await project_sandbox(RUNTIME_ERROR_PROJECT)
        result = await TestingValidationAgent(sandbox=sb, sandbox_id=sandbox_id).run_testing_pipeline()

        assert result.passed is False
        combined = " ".join(result.likely_causes) + result.stdout + result.stderr
        assert "KeyError" in combined

    @pytest.mark.asyncio
    async def test_a_project_with_no_tests_is_not_reported_as_passing(self, project_sandbox):
        sb, sandbox_id = await project_sandbox({"module.py": "VALUE = 1\n", "conftest.py": ""})
        result = await TestingValidationAgent(sandbox=sb, sandbox_id=sandbox_id).run_testing_pipeline()

        assert result.passed is False, "zero collected tests must never count as success"

    @pytest.mark.asyncio
    async def test_test_output_is_capped(self, project_sandbox):
        noisy = {
            "conftest.py": "",
            "tests/test_noise.py": """
                def test_noisy():
                    print('N' * 300000)
                    assert True
            """,
        }
        sb, sandbox_id = await project_sandbox(noisy)
        agent = TestingValidationAgent(sandbox=sb, sandbox_id=sandbox_id)
        result = await agent.run_testing_pipeline()
        assert len(result.stdout) <= agent.limits.max_output_chars


# --------------------------------------------------------------- tool failure
class TestToolFailureHandling:
    @pytest.mark.asyncio
    async def test_tool_failure_is_reported_not_raised(self, sandbox):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()
        result = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": "does/not/exist.py"}, run=make_run(),
        )
        assert result.success is False
        assert result.error
        assert layer.audit_records, "the failure must still be audited"

    @pytest.mark.asyncio
    async def test_a_failing_tool_does_not_poison_the_next_call(self, sandbox):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()
        run = make_run()

        bad = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": "missing.py"}, run=run,
        )
        good = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
            args={"file_path": "recovered.py", "content": "ok"}, run=run,
        )
        assert bad.success is False
        assert good.success is True

    @pytest.mark.asyncio
    async def test_transient_sandbox_errors_are_visible_to_the_caller(self):
        """The platform has no automatic retry, so a transient container error must
        at least surface accurately instead of being silently swallowed."""
        sb = FlakySandbox(fail_times=2)
        sandbox_id = await sb.create_sandbox("flaky")
        layer = ControlledToolLayer()
        run = make_run()

        first = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="list_files",
            args={"directory_path": "."}, run=run,
        )
        assert first.success is False
        assert "transient container error" in (first.error or "")

        second = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="list_files",
            args={"directory_path": "."}, run=run,
        )
        assert second.success is False  # attempt 2 also fails

        third = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="list_files",
            args={"directory_path": "."}, run=run,
        )
        assert third.success is True, "the sandbox recovered but the layer did not"
        assert sb.attempts == 3

    @pytest.mark.asyncio
    async def test_hard_sandbox_failure_is_reported_as_execution_error(self):
        sb = FailingSandbox()
        with pytest.raises(SandboxExecutionError):
            await sb.create_sandbox("dead")

    @pytest.mark.asyncio
    async def test_timeout_is_enforced_per_tool(self, sandbox):
        sb = HangingSandbox(delay_seconds=10)
        sandbox_id = await sb.create_sandbox("slow")
        layer = ControlledToolLayer()
        tool = layer.registry.get_tool("search_files")
        original = tool.timeout_seconds
        tool.timeout_seconds = 1
        try:
            result = await layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="search_files",
                args={"query": "anything"}, run=make_run(),
            )
        finally:
            tool.timeout_seconds = original

        assert result.success is False
        assert result.exit_code == 124


# ------------------------------------------------------------ repeated failure
class TestRepeatedFailureSafeguards:
    def test_an_identical_failed_patch_is_blocked_the_second_time(self):
        manager = CodingSafeguardManager()
        content = "def broken():\n    return undefined_name\n"

        manager.record_modification_attempt(
            file_path="module.py",
            patch_or_new_content=content,
            content_before="",
            content_after=content,
            success=False,
            error="NameError",
        )

        with pytest.raises(SafeguardViolationError, match="Repeated Identical Fix"):
            manager.check_repeated_fix_safeguard("module.py", content)

    def test_a_different_patch_is_allowed_after_a_failure(self):
        manager = CodingSafeguardManager()
        manager.record_modification_attempt(
            file_path="module.py",
            patch_or_new_content="attempt one",
            content_before="",
            content_after="attempt one",
            success=False,
            error="NameError",
        )
        manager.check_repeated_fix_safeguard("module.py", "attempt two, genuinely different")

    def test_endless_rewriting_of_one_file_is_capped(self):
        manager = CodingSafeguardManager()
        raised = None
        for index in range(50):
            try:
                manager.check_infinite_loop_safeguard("churn.py")
                manager.record_modification_attempt(
                    file_path="churn.py",
                    patch_or_new_content=f"version {index}",
                    content_before="",
                    content_after=f"version {index}",
                    success=False,
                    error="still broken",
                )
            except SafeguardViolationError as exc:
                raised = exc
                break
        assert raised is not None, "unbounded rewriting of the same file was permitted"
        assert "Loop" in str(raised) or "loop" in str(raised)

    def test_deleting_a_critical_file_is_blocked(self):
        manager = CodingSafeguardManager()
        with pytest.raises(SafeguardViolationError):
            manager.check_deletion_safeguard("requirements.txt")


# ------------------------------------------------------ workspace degradation
class TestWorkspaceDegradation:
    @pytest.mark.asyncio
    async def test_destroying_the_sandbox_mid_flight_is_handled(self):
        sb = InProcessSandbox()
        sandbox_id = await sb.create_sandbox("vanishing")
        await sb.write_file(sandbox_id, "a.py", "x")
        await sb.destroy_sandbox(sandbox_id)

        layer = ControlledToolLayer()
        result = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
            args={"file_path": "a.py"}, run=make_run(),
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_unwritable_target_is_reported(self, sandbox, monkeypatch):
        sb, sandbox_id = sandbox

        async def exploding_write(*_args, **_kwargs):
            raise OSError("[Errno 28] No space left on device")

        monkeypatch.setattr(sb, "write_file", exploding_write)
        layer = ControlledToolLayer()
        result = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
            args={"file_path": "out.py", "content": "x"}, run=make_run(),
        )
        assert result.success is False
        assert "No space left" in (result.error or "")
