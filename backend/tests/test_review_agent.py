import json
import pytest
from typing import List, Dict, Any, AsyncIterator, Optional

from app.domain.entities.review_agent import (
    ReviewSeverity,
    ReviewCategory,
    ReviewFinding,
    ReviewResult,
    ALL_REVIEW_CATEGORIES,
)
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage, LLMResponse
from app.domain.interfaces.sandbox import SandboxInterface, CommandResult
from app.application.agent.subagents.reviewer import ReviewAgent


class MockAIProvider(AIProviderInterface):
    """Mock LLM Provider returning controlled review responses."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_messages: List[LLMMessage] = []

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.last_messages = messages
        return LLMResponse(content=self.response_text, tool_calls=[])

    async def stream_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        yield self.response_text


class MockReadOnlySandbox(SandboxInterface):
    """Mock sandbox to verify that ReviewAgent only calls read-only methods."""

    def __init__(self):
        self.write_called = False
        self.executed_commands: List[str] = []

    async def create_sandbox(self, session_id: str, workspace_path: str = ".") -> str:
        return "sb_123"

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120) -> CommandResult:
        self.executed_commands.append(command)
        return CommandResult(command=command, exit_code=0, stdout="git status clean", stderr="", duration_ms=10)

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        self.write_called = True
        raise RuntimeError("ReviewAgent must NOT write files directly!")

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        return "def test_func(): pass"

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        return True


def test_review_categories_and_severities():
    """Verify all 12 categories and 5 severities are defined."""
    assert len(ALL_REVIEW_CATEGORIES) == 12
    expected_categories = {
        "correctness",
        "requirements_coverage",
        "security",
        "error_handling",
        "maintainability",
        "code_quality",
        "duplicated_code",
        "unused_code",
        "test_coverage",
        "performance_concerns",
        "dependency_risks",
        "configuration_mistakes",
    }
    assert {c.value for c in ALL_REVIEW_CATEGORIES} == expected_categories

    severities = {s.value for s in ReviewSeverity}
    assert severities == {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}


def test_review_result_post_init_logic():
    """Verify blocking findings count and requires_another_cycle calculations."""
    f1 = ReviewFinding(
        finding="SQL Injection vulnerability",
        severity=ReviewSeverity.CRITICAL,
        affected_file="app/db.py",
        explanation="Raw SQL query concatenation",
        recommended_fix="Use parameterized queries",
        category=ReviewCategory.SECURITY,
    )
    f2 = ReviewFinding(
        finding="Missing docstring",
        severity=ReviewSeverity.LOW,
        affected_file="app/utils.py",
        explanation="No docstring provided",
        recommended_fix="Add docstring",
        category=ReviewCategory.CODE_QUALITY,
    )

    res = ReviewResult(
        passed=False,
        summary="Review completed with critical finding.",
        findings=[f1, f2],
    )

    assert res.blocking_findings_count == 1
    assert res.requires_another_cycle is True
    assert "CRITICAL" in res.to_markdown()
    assert "app/db.py" in res.to_markdown()


@pytest.mark.asyncio
async def test_review_agent_read_only_guarantee():
    """Verify ReviewAgent does not write files or modify code directly."""
    provider = MockAIProvider(
        json.dumps({
            "passed": True,
            "summary": "Code review passed.",
            "findings": []
        })
    )
    sandbox = MockReadOnlySandbox()
    reviewer = ReviewAgent(provider, sandbox, "sb_123")

    result = await reviewer.review_final_code_structured(
        requirement="Build auth endpoint",
        modified_files=["app/main.py"],
    )

    assert result.passed is True
    assert sandbox.write_called is False  # Guaranteed read-only!


@pytest.mark.asyncio
async def test_review_agent_parses_all_fields_and_severities():
    """Verify structured parsing of finding, severity, affected_file, explanation, recommended_fix."""
    mock_findings = [
        {
            "finding": "Hardcoded Secret",
            "severity": "HIGH",
            "affected_file": "app/core/config.py",
            "explanation": "JWT key is hardcoded as plain string",
            "recommended_fix": "Load secret from environment variable",
            "category": "security",
        },
        {
            "finding": "Unused variable",
            "severity": "INFO",
            "affected_file": "app/services/user.py",
            "explanation": "Variable `temp` is declared but never read",
            "recommended_fix": "Remove unused variable",
            "category": "unused_code",
        },
    ]

    provider_response = json.dumps({
        "passed": False,
        "summary": "High severity security finding detected.",
        "findings": mock_findings,
    })

    provider = MockAIProvider(provider_response)
    sandbox = MockReadOnlySandbox()
    reviewer = ReviewAgent(provider, sandbox, "sb_123")

    result = await reviewer.review_final_code_structured(
        requirement="Secure config",
        plan="Step 1 replace hardcoded secret",
    )

    assert result.passed is False
    assert result.blocking_findings_count == 1
    assert len(result.findings) == 2

    h_finding = result.findings[0]
    assert h_finding.finding == "Hardcoded Secret"
    assert h_finding.severity == ReviewSeverity.HIGH
    assert h_finding.affected_file == "app/core/config.py"
    assert h_finding.explanation == "JWT key is hardcoded as plain string"
    assert h_finding.recommended_fix == "Load secret from environment variable"
    assert h_finding.category == ReviewCategory.SECURITY
