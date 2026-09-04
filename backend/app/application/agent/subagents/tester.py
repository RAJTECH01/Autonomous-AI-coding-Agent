import time
from typing import Dict, Any, List, Optional
from app.domain.entities.testing_agent import (
    FailingTestDetail,
    ParsedTestOutput,
    TestResourceLimits,
    StructuredTestResult,
)
from app.application.agent.testing.test_adapters import TestRunnerRegistry, BaseTestRunnerAdapter
from app.domain.interfaces.ai_provider import AIProviderInterface
from app.domain.interfaces.sandbox import SandboxInterface
from app.core.logging import logger


class TestingValidationAgent:
    """
    Subagent responsible for automated testing, framework detection, targeted-first execution,
    signal capture, framework output parsing, and structured test reporting.
    """
    __test__ = False

    def __init__(
        self,
        sandbox: SandboxInterface,
        sandbox_id: str,
        provider: Optional[AIProviderInterface] = None,
        registry: Optional[TestRunnerRegistry] = None,
        limits: Optional[TestResourceLimits] = None,
    ):
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id
        self.provider = provider
        self.registry = registry or TestRunnerRegistry()
        self.limits = limits or TestResourceLimits()

    async def run_testing_pipeline(
        self,
        modified_files: Optional[List[str]] = None,
        custom_test_path: Optional[str] = None,
    ) -> StructuredTestResult:
        """
        Executes full testing pipeline:
          1. Detect testing framework
          2. Discover workspace files & identify targeted tests
          3. Stage 1: Run targeted tests first (halt if failed)
          4. Stage 2: Run broader tests after targeted tests pass
          5. Parse results & return StructuredTestResult
        """
        logger.info("Starting Testing & Validation Agent pipeline")
        start_time = time.time()

        # Step 1: Discover workspace files
        workspace_files = await self._discover_workspace_files()

        # Step 2: Detect test runner adapter
        adapter = self.registry.detect_adapter(workspace_files)

        # Step 3: Identify targeted tests
        modified = modified_files or []
        targeted_tests = []
        if custom_test_path:
            targeted_tests = [custom_test_path]
        else:
            targeted_tests = adapter.identify_targeted_tests(modified, workspace_files)

        targeted_tests_run: List[str] = []
        broader_tests_run: List[str] = []

        stdout_captured = ""
        stderr_captured = ""
        final_exit_code = 0
        parsed_result: Optional[ParsedTestOutput] = None

        # Stage 1: Run Targeted Tests First
        if targeted_tests:
            logger.info("Stage 1: Running targeted tests first", targeted_tests=targeted_tests)
            targeted_cmd = adapter.build_test_command(targeted_tests, self.limits)
            targeted_tests_run = targeted_tests

            target_res = await self._execute_test_command(targeted_cmd)
            stdout_captured += f"--- Stage 1: Targeted Tests ({targeted_cmd}) ---\n{target_res['stdout']}\n"
            stderr_captured += target_res['stderr']
            final_exit_code = target_res['exit_code']

            parsed_result = adapter.parse_output(
                exit_code=target_res['exit_code'],
                stdout=target_res['stdout'],
                stderr=target_res['stderr'],
            )

            # If targeted tests fail, halt pipeline immediately
            if not parsed_result.passed:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.warning("Stage 1: Targeted tests failed. Halting testing pipeline.")
                return StructuredTestResult(
                    framework=adapter.framework_name,
                    language=adapter.language,
                    targeted_tests_run=targeted_tests_run,
                    broader_tests_run=[],
                    passed=False,
                    total_tests=parsed_result.total_count,
                    passed_count=parsed_result.passed_count,
                    failed_count=parsed_result.failed_count,
                    skipped_count=parsed_result.skipped_count,
                    duration_ms=duration_ms,
                    exit_code=final_exit_code,
                    stdout=stdout_captured[:self.limits.max_output_chars],
                    stderr=stderr_captured[:self.limits.max_output_chars],
                    failing_tests=parsed_result.failing_tests,
                    likely_causes=parsed_result.likely_causes,
                    summary=f"Targeted Tests Failed: {parsed_result.summary}",
                )

        # Stage 2: Run Broader Tests After Successful Targeted Tests
        logger.info("Stage 2: Executing broader test suite")
        broader_cmd = adapter.build_test_command(test_paths=None, limits=self.limits)
        broader_tests_run = [broader_cmd]

        broader_res = await self._execute_test_command(broader_cmd)
        stdout_captured += f"\n--- Stage 2: Broader Suite ({broader_cmd}) ---\n{broader_res['stdout']}\n"
        if broader_res['stderr']:
            stderr_captured += f"\n{broader_res['stderr']}"
        final_exit_code = broader_res['exit_code']

        parsed_broader = adapter.parse_output(
            exit_code=broader_res['exit_code'],
            stdout=broader_res['stdout'],
            stderr=broader_res['stderr'],
        )

        duration_ms = int((time.time() - start_time) * 1000)

        # Combine metrics
        total_tests = (parsed_result.total_count if parsed_result else 0) + parsed_broader.total_count
        passed_count = (parsed_result.passed_count if parsed_result else 0) + parsed_broader.passed_count
        failed_count = (parsed_result.failed_count if parsed_result else 0) + parsed_broader.failed_count
        skipped_count = (parsed_result.skipped_count if parsed_result else 0) + parsed_broader.skipped_count

        combined_failing = (parsed_result.failing_tests if parsed_result else []) + parsed_broader.failing_tests
        combined_causes = sorted(list(set((parsed_result.likely_causes if parsed_result else []) + parsed_broader.likely_causes)))

        overall_passed = parsed_broader.passed and (not parsed_result or parsed_result.passed)

        summary = (
            f"Full Validation: {'PASSED' if overall_passed else 'FAILED'} | "
            f"Targeted: {len(targeted_tests_run)} run, Broader: {parsed_broader.summary}"
        )

        return StructuredTestResult(
            framework=adapter.framework_name,
            language=adapter.language,
            targeted_tests_run=targeted_tests_run,
            broader_tests_run=broader_tests_run,
            passed=overall_passed,
            total_tests=total_tests,
            passed_count=passed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            duration_ms=duration_ms,
            exit_code=final_exit_code,
            stdout=stdout_captured[:self.limits.max_output_chars],
            stderr=stderr_captured[:self.limits.max_output_chars],
            failing_tests=combined_failing,
            likely_causes=combined_causes,
            summary=summary,
        )

    async def _discover_workspace_files(self) -> List[str]:
        try:
            cmd_res = await self.sandbox.execute_command(self.sandbox_id, "find . -maxdepth 4 -not -path '*/.*'", timeout_seconds=15)
            if cmd_res.exit_code == 0:
                lines = [line.strip() for line in cmd_res.stdout.splitlines() if line.strip()]
                return lines
        except Exception as e:
            logger.warning("Could not list workspace files for test detection", error=str(e))
        return []

    async def _execute_test_command(self, command: str) -> Dict[str, Any]:
        """Execute command enforcing timeout and stdout/stderr capture bounds."""
        try:
            res = await self.sandbox.execute_command(
                self.sandbox_id,
                command,
                timeout_seconds=self.limits.timeout_seconds,
            )
            stdout = res.stdout[:self.limits.max_output_chars] if res.stdout else ""
            stderr = res.stderr[:self.limits.max_output_chars] if res.stderr else ""
            return {"exit_code": res.exit_code, "stdout": stdout, "stderr": stderr}
        except Exception as e:
            return {"exit_code": 124, "stdout": "", "stderr": f"Execution error/timeout: {str(e)}"}
