from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


@dataclass
class FailingTestDetail:
    """Detailed record of a single failing test case."""
    test_name: str
    file_path: str
    line_number: Optional[int] = None
    failure_message: str = ""
    likely_cause: str = "Unknown"
    stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "failure_message": self.failure_message,
            "likely_cause": self.likely_cause,
            "stack_trace": self.stack_trace,
        }


@dataclass
class ParsedTestOutput:
    """Parsed metrics extracted from test runner execution output."""
    passed: bool
    total_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    failing_tests: List[FailingTestDetail] = field(default_factory=list)
    likely_causes: List[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class TestResourceLimits:
    """Resource bounds enforced during test execution."""
    __test__ = False
    timeout_seconds: int = 60
    max_output_chars: int = 50_000
    max_memory_mb: int = 512
    max_processes: int = 10


@dataclass
class StructuredTestResult:
    """Structured result returned to CodingAgent and StateMachine."""
    framework: str
    language: str
    targeted_tests_run: List[str]
    broader_tests_run: List[str]
    passed: bool
    total_tests: int
    passed_count: int
    failed_count: int
    skipped_count: int
    duration_ms: int
    exit_code: int
    stdout: str
    stderr: str
    failing_tests: List[FailingTestDetail] = field(default_factory=list)
    likely_causes: List[str] = field(default_factory=list)
    summary: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "framework": self.framework,
            "language": self.language,
            "targeted_tests_run": self.targeted_tests_run,
            "broader_tests_run": self.broader_tests_run,
            "passed": self.passed,
            "total_tests": self.total_tests,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:2000],  # Truncated summary for logs
            "stderr": self.stderr[:2000],
            "failing_tests": [ft.to_dict() for ft in self.failing_tests],
            "likely_causes": self.likely_causes,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
        }
