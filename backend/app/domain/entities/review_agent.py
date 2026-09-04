from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional


class ReviewSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ReviewCategory(str, Enum):
    CORRECTNESS = "correctness"
    REQUIREMENTS_COVERAGE = "requirements_coverage"
    SECURITY = "security"
    ERROR_HANDLING = "error_handling"
    MAINTAINABILITY = "maintainability"
    CODE_QUALITY = "code_quality"
    DUPLICATED_CODE = "duplicated_code"
    UNUSED_CODE = "unused_code"
    TEST_COVERAGE = "test_coverage"
    PERFORMANCE_CONCERNS = "performance_concerns"
    DEPENDENCY_RISKS = "dependency_risks"
    CONFIGURATION_MISTAKES = "configuration_mistakes"


ALL_REVIEW_CATEGORIES: List[ReviewCategory] = [
    ReviewCategory.CORRECTNESS,
    ReviewCategory.REQUIREMENTS_COVERAGE,
    ReviewCategory.SECURITY,
    ReviewCategory.ERROR_HANDLING,
    ReviewCategory.MAINTAINABILITY,
    ReviewCategory.CODE_QUALITY,
    ReviewCategory.DUPLICATED_CODE,
    ReviewCategory.UNUSED_CODE,
    ReviewCategory.TEST_COVERAGE,
    ReviewCategory.PERFORMANCE_CONCERNS,
    ReviewCategory.DEPENDENCY_RISKS,
    ReviewCategory.CONFIGURATION_MISTAKES,
]


@dataclass
class ReviewFinding:
    """Structured code review finding."""
    finding: str
    severity: ReviewSeverity
    affected_file: str
    explanation: str
    recommended_fix: str
    category: ReviewCategory = ReviewCategory.CODE_QUALITY

    def to_dict(self) -> Dict[str, Any]:
        severity_val = self.severity.value if isinstance(self.severity, ReviewSeverity) else str(self.severity)
        category_val = self.category.value if isinstance(self.category, ReviewCategory) else str(self.category)
        return {
            "finding": self.finding,
            "severity": severity_val,
            "affected_file": self.affected_file,
            "explanation": self.explanation,
            "recommended_fix": self.recommended_fix,
            "category": category_val,
        }


@dataclass
class ReviewResult:
    """Structured result produced by the Final Code-Review Agent."""
    passed: bool
    summary: str
    findings: List[ReviewFinding] = field(default_factory=list)
    categories_evaluated: List[ReviewCategory] = field(default_factory=lambda: list(ALL_REVIEW_CATEGORIES))
    requires_another_cycle: bool = False
    blocking_findings_count: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        # Calculate blocking findings (CRITICAL and HIGH severities)
        blocking_severities = {ReviewSeverity.CRITICAL, ReviewSeverity.HIGH, "CRITICAL", "HIGH"}
        self.blocking_findings_count = sum(
            1 for f in self.findings if f.severity in blocking_severities
        )
        # Determine if another implementation cycle is required
        if self.blocking_findings_count > 0 or not self.passed:
            self.requires_another_cycle = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "categories_evaluated": [c.value if isinstance(c, ReviewCategory) else str(c) for c in self.categories_evaluated],
            "requires_another_cycle": self.requires_another_cycle,
            "blocking_findings_count": self.blocking_findings_count,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_markdown(self) -> str:
        status_str = "PASSED" if self.passed else "REQUIRES REVISION"
        md = [
            f"# Final Code Review Report - [{status_str}]",
            f"**Overall Result:** `{status_str}` | **Blocking Findings:** `{self.blocking_findings_count}` | **Total Findings:** `{len(self.findings)}`",
            "",
            "## Summary",
            self.summary,
            "",
            "## Evaluated Categories",
        ]
        cat_labels = [f"- `{c.value if isinstance(c, ReviewCategory) else str(c)}`" for c in self.categories_evaluated]
        md.extend(cat_labels)
        md.append("")
        md.append("## Findings")

        if not self.findings:
            md.append("No issues found. Code satisfies all review criteria.")
        else:
            # Group by severity
            for sev in [ReviewSeverity.CRITICAL, ReviewSeverity.HIGH, ReviewSeverity.MEDIUM, ReviewSeverity.LOW, ReviewSeverity.INFO]:
                sev_findings = [f for f in self.findings if (f.severity.value if isinstance(f.severity, ReviewSeverity) else f.severity) == sev.value]
                if sev_findings:
                    md.append(f"### Severity: {sev.value}")
                    for idx, f in enumerate(sev_findings, 1):
                        category_str = f.category.value if isinstance(f.category, ReviewCategory) else f.category
                        md.extend([
                            f"#### {idx}. {f.finding} (`{sev.value}`)",
                            f"- **Category:** `{category_str}`",
                            f"- **Affected File:** `{f.affected_file}`",
                            f"- **Explanation:** {f.explanation}",
                            f"- **Recommended Fix:** {f.recommended_fix}",
                            "",
                        ])

        return "\n".join(md)
