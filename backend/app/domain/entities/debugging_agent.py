from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


@dataclass
class DebugInputContext:
    """Inputs supplied to the Debugging Agent for error diagnosis."""
    requirement: str
    implementation_plan: Optional[str] = None
    changed_files: List[str] = field(default_factory=list)
    test_results: Optional[Any] = None
    runtime_errors: Optional[str] = None
    compiler_errors: Optional[str] = None
    logs: Optional[str] = None

    def to_summary_text(self) -> str:
        parts = [
            f"=== Requirement ===\n{self.requirement}",
            f"=== Changed Files ===\n{', '.join(self.changed_files) if self.changed_files else 'None'}",
        ]
        if self.implementation_plan:
            parts.append(f"=== Implementation Plan ===\n{self.implementation_plan}")
        if self.test_results:
            parts.append(f"=== Test Results ===\n{str(self.test_results)}")
        if self.compiler_errors:
            parts.append(f"=== Compiler Errors ===\n{self.compiler_errors}")
        if self.runtime_errors:
            parts.append(f"=== Runtime Errors ===\n{self.runtime_errors}")
        if self.logs:
            parts.append(f"=== System Logs ===\n{self.logs}")
        return "\n\n".join(parts)


@dataclass
class ValidationComparison:
    """Comparison metrics evaluating test results before and after a debug fix."""
    passed: bool
    previous_failed_count: int
    current_failed_count: int
    tests_fixed_count: int
    new_regressions_count: int
    delta_summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "previous_failed_count": self.previous_failed_count,
            "current_failed_count": self.current_failed_count,
            "tests_fixed_count": self.tests_fixed_count,
            "new_regressions_count": self.new_regressions_count,
            "delta_summary": self.delta_summary,
        }


@dataclass
class StructuredDebugResult:
    """Structured debug result object returned by DebuggingAgent."""
    root_cause: str
    affected_files: List[str]
    proposed_fix: str
    applied_changes: List[Dict[str, Any]]
    validation_result: ValidationComparison
    confidence: float  # 0.0 to 1.0
    loop_detected: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_cause": self.root_cause,
            "affected_files": self.affected_files,
            "proposed_fix": self.proposed_fix,
            "applied_changes": self.applied_changes,
            "validation_result": self.validation_result.to_dict(),
            "confidence": self.confidence,
            "loop_detected": self.loop_detected,
            "timestamp": self.timestamp.isoformat(),
        }
