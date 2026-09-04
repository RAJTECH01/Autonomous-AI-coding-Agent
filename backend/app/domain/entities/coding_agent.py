from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


class SafeguardViolationError(Exception):
    """Raised when an operation violates agent code modification safeguards."""
    pass


@dataclass
class FileVersionSnapshot:
    """Snapshot of a file's state prior to modification."""
    snapshot_id: str
    file_path: str
    content_hash: str
    line_count: int
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "file_path": self.file_path,
            "content_hash": self.content_hash,
            "line_count": self.line_count,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FileChangeRecord:
    """Structured record of a single file modification or creation."""
    file_path: str
    change_type: str  # 'create', 'modify', 'delete'
    lines_added: int
    lines_deleted: int
    lines_changed: int
    reason: str
    related_requirement: str
    related_test: Optional[str] = None
    previous_version_metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "change_type": self.change_type,
            "lines_added": self.lines_added,
            "lines_deleted": self.lines_deleted,
            "lines_changed": self.lines_changed,
            "reason": self.reason,
            "related_requirement": self.related_requirement,
            "related_test": self.related_test,
            "previous_version_metadata": self.previous_version_metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PatchAttempt:
    """Metadata tracking an attempted patch / code modification on a file."""
    file_path: str
    patch_hash: str
    content_hash_before: str
    content_hash_after: str
    success: bool
    error: Optional[str] = None
    iteration: int = 1
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StructuredFailureReport:
    """Structured report returned when a coding task fails repeatedly or triggers safeguards."""
    task_id: str
    run_id: str
    failure_reason: str
    failing_stage: str
    root_cause_analysis: str
    stack_trace_or_error: str
    modified_files: List[str] = field(default_factory=list)
    attempted_fixes_count: int = 0
    repeated_fix_detected: bool = False
    infinite_loop_detected: bool = False
    recommendations: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_markdown(self) -> str:
        md = [
            f"# Coding Task Failure Report",
            f"**Task ID:** `{self.task_id}` | **Run ID:** `{self.run_id}`",
            f"**Failure Reason:** {self.failure_reason}",
            f"**Failing Stage:** `{self.failing_stage}`",
            f"**Attempted Fixes:** {self.attempted_fixes_count}",
            f"**Repeated Fix Detected:** `{self.repeated_fix_detected}`",
            f"**Infinite Loop Detected:** `{self.infinite_loop_detected}`",
            "",
            "## Root Cause Analysis",
            self.root_cause_analysis,
            "",
            "## Error / Stack Trace",
            "```",
            self.stack_trace_or_error,
            "```",
            "",
            "## Files Modified",
        ]
        for f in self.modified_files:
            md.append(f"- `{f}`")
        if not self.modified_files:
            md.append("- None")

        md.extend(["", "## Actionable Recommendations"])
        for rec in self.recommendations:
            md.append(f"1. {rec}")
        if not self.recommendations:
            md.append("- Inspect environment or requirements manually.")

        return "\n".join(md)
