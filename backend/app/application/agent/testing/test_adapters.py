import os
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set
from app.domain.entities.testing_agent import (
    FailingTestDetail,
    ParsedTestOutput,
    TestResourceLimits,
)
from app.core.logging import logger


class BaseTestRunnerAdapter(ABC):
    """Abstract base class for language and framework-specific test runner adapters."""

    @property
    @abstractmethod
    def framework_name(self) -> str:
        pass

    @property
    @abstractmethod
    def language(self) -> str:
        pass

    @abstractmethod
    def detect(self, workspace_files: List[str]) -> bool:
        """Return True if workspace matches this test framework's signature."""
        pass

    @abstractmethod
    def identify_targeted_tests(
        self,
        modified_files: List[str],
        workspace_files: List[str],
    ) -> List[str]:
        """Identify specific test files/functions directly relevant to modified source files."""
        pass

    @abstractmethod
    def build_test_command(
        self,
        test_paths: Optional[List[str]] = None,
        limits: Optional[TestResourceLimits] = None,
    ) -> str:
        """Construct framework test command line string."""
        pass

    @abstractmethod
    def parse_output(self, exit_code: int, stdout: str, stderr: str) -> ParsedTestOutput:
        """Parse framework stdout/stderr into structured ParsedTestOutput metrics."""
        pass


class PytestAdapter(BaseTestRunnerAdapter):
    """Python pytest framework adapter."""

    @property
    def framework_name(self) -> str:
        return "pytest"

    @property
    def language(self) -> str:
        return "python"

    def detect(self, workspace_files: List[str]) -> bool:
        signatures = {"pytest.ini", "conftest.py", "pyproject.toml", "setup.cfg"}
        for f in workspace_files:
            clean = os.path.basename(f).lower()
            if clean in signatures or clean.startswith("test_") or clean.endswith("_test.py"):
                return True
        return False

    def identify_targeted_tests(
        self,
        modified_files: List[str],
        workspace_files: List[str],
    ) -> List[str]:
        targeted: Set[str] = set()
        workspace_set = {os.path.normpath(f).replace("\\", "/"): f for f in workspace_files}

        for mod in modified_files:
            norm_mod = os.path.normpath(mod).replace("\\", "/")
            basename = os.path.basename(norm_mod)
            name_without_ext = os.path.splitext(basename)[0]

            # Direct candidates
            candidates = [
                f"tests/test_{basename}",
                f"tests/{name_without_ext}_test.py",
                f"tests/test_{name_without_ext}.py",
                f"test_{basename}",
                f"{name_without_ext}_test.py",
            ]

            # Search in workspace_files for candidate matches
            for cand in candidates:
                cand_norm = os.path.normpath(cand).replace("\\", "/")
                for w_norm, original_path in workspace_set.items():
                    if w_norm == cand_norm or w_norm.endswith("/" + cand_norm) or cand_norm.endswith("/" + w_norm):
                        targeted.add(original_path)

            # If modified file is already a test file itself
            if "test_" in basename or "_test" in basename:
                targeted.add(mod)

        return sorted(list(targeted))

    def build_test_command(
        self,
        test_paths: Optional[List[str]] = None,
        limits: Optional[TestResourceLimits] = None,
    ) -> str:
        cmd_parts = ["pytest", "-v"]
        if test_paths:
            cmd_parts.extend(test_paths)
        return " ".join(cmd_parts)

    def parse_output(self, exit_code: int, stdout: str, stderr: str) -> ParsedTestOutput:
        combined = f"{stdout}\n{stderr}"
        failing_tests: List[FailingTestDetail] = []
        likely_causes: Set[str] = set()

        # Parse summary stats line: e.g. "3 passed, 1 failed, 1 skipped in 0.12s" or "1 failed in 0.05s"
        passed_count = 0
        failed_count = 0
        skipped_count = 0

        passed_match = re.search(r"(\d+)\s+passed", combined)
        if passed_match:
            passed_count = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", combined)
        if failed_match:
            failed_count = int(failed_match.group(1))

        error_match = re.search(r"(\d+)\s+error", combined)
        if error_match:
            failed_count += int(error_match.group(1))

        skipped_match = re.search(r"(\d+)\s+skipped", combined)
        if skipped_match:
            skipped_count = int(skipped_match.group(1))

        total_count = passed_count + failed_count + skipped_count

        # Parse failed test details: e.g. "FAILED tests/test_auth.py::test_login - AssertionError: assert False"
        failed_lines = re.findall(r"FAILED\s+([^\s:]+)(?:::(.+?))?\s+-\s+(.+)", combined)
        for path, test_func, msg in failed_lines:
            test_name = f"{path}::{test_func}" if test_func else path
            cause = self._classify_likely_cause(msg)
            likely_causes.add(cause)

            # Try extracting line number from traceback block
            line_no = None
            line_match = re.search(re.escape(path) + r":(\d+):", combined)
            if line_match:
                line_no = int(line_match.group(1))

            failing_tests.append(
                FailingTestDetail(
                    test_name=test_name,
                    file_path=path,
                    line_number=line_no,
                    failure_message=msg.strip(),
                    likely_cause=cause,
                    stack_trace=combined[:2000],
                )
            )

        # Fallback if failed exit code but no FAILED lines parsed cleanly
        if exit_code != 0 and not failing_tests:
            cause = self._classify_likely_cause(combined)
            likely_causes.add(cause)
            failing_tests.append(
                FailingTestDetail(
                    test_name="TestSuiteExecution",
                    file_path="tests",
                    failure_message=combined[-300:] if combined else "Test suite failed",
                    likely_cause=cause,
                    stack_trace=combined[:2000],
                )
            )

        # NEVER treat exit_code == 0 as passed if 0 tests ran!
        is_passed = (exit_code == 0) and (total_count > 0) and (failed_count == 0)

        summary = (
            f"Pytest Result: {'PASSED' if is_passed else 'FAILED'} | "
            f"Total: {total_count}, Passed: {passed_count}, Failed: {failed_count}, Skipped: {skipped_count}"
        )

        return ParsedTestOutput(
            passed=is_passed,
            total_count=total_count,
            passed_count=passed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            failing_tests=failing_tests,
            likely_causes=sorted(list(likely_causes)),
            summary=summary,
        )

    def _classify_likely_cause(self, error_text: str) -> str:
        if "AssertionError" in error_text:
            return "Assertion Failure: Value did not match expectation"
        if "KeyError" in error_text:
            return "KeyError: Missing expected dictionary key or payload attribute"
        if "AttributeError" in error_text:
            return "AttributeError: Attempted accessing non-existent attribute"
        if "TypeError" in error_text:
            return "TypeError: Incorrect argument type or signature mismatch"
        if "ModuleNotFoundError" in error_text or "ImportError" in error_text:
            return "Import Error: Missing module or broken import statement"
        if "SyntaxError" in error_text or "IndentationError" in error_text:
            return "Syntax Error: Code syntax or indentation error"
        if "Timeout" in error_text:
            return "Timeout Error: Test execution timed out"
        return "Runtime Error: Unhandled exception during test execution"


class JestAdapter(BaseTestRunnerAdapter):
    """JavaScript / TypeScript Jest framework adapter."""

    @property
    def framework_name(self) -> str:
        return "jest"

    @property
    def language(self) -> str:
        return "javascript"

    def detect(self, workspace_files: List[str]) -> bool:
        for f in workspace_files:
            clean = os.path.basename(f).lower()
            if clean in {"jest.config.js", "jest.config.ts"} or clean.endswith(".test.js") or clean.endswith(".test.ts"):
                return True
        return False

    def identify_targeted_tests(self, modified_files: List[str], workspace_files: List[str]) -> List[str]:
        targeted: List[str] = []
        for mod in modified_files:
            base = os.path.splitext(mod)[0]
            cand = f"{base}.test.js"
            if cand in workspace_files:
                targeted.append(cand)
        return targeted

    def build_test_command(self, test_paths: Optional[List[str]] = None, limits: Optional[TestResourceLimits] = None) -> str:
        cmd_parts = ["npx", "jest"]
        if test_paths:
            cmd_parts.extend(test_paths)
        return " ".join(cmd_parts)

    def parse_output(self, exit_code: int, stdout: str, stderr: str) -> ParsedTestOutput:
        combined = f"{stdout}\n{stderr}"
        passed = exit_code == 0 and "Tests:" in combined and "failed" not in combined
        return ParsedTestOutput(
            passed=passed,
            total_count=1 if passed else 0,
            passed_count=1 if passed else 0,
            failed_count=0 if passed else 1,
            summary=f"Jest execution {'passed' if passed else 'failed'}",
        )


class TestRunnerRegistry:
    """Registry managing available test framework adapters."""
    __test__ = False

    def __init__(self):
        self.adapters: List[BaseTestRunnerAdapter] = [
            PytestAdapter(),
            JestAdapter(),
        ]

    def register_adapter(self, adapter: BaseTestRunnerAdapter) -> None:
        self.adapters.append(adapter)

    def detect_adapter(self, workspace_files: List[str]) -> BaseTestRunnerAdapter:
        for adapter in self.adapters:
            if adapter.detect(workspace_files):
                logger.info(f"Detected test framework: {adapter.framework_name} ({adapter.language})")
                return adapter
        # Default fallback to PytestAdapter
        return PytestAdapter()
