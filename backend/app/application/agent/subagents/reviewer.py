import json
import re
from typing import Dict, Any, List, Optional
from app.domain.entities.review_agent import (
    ReviewSeverity,
    ReviewCategory,
    ReviewFinding,
    ReviewResult,
    ALL_REVIEW_CATEGORIES,
)
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage
from app.domain.interfaces.sandbox import SandboxInterface
from app.core.logging import logger


from app.core.prompts.manager import PromptManager, get_prompt_manager
from app.schemas.prompts import PromptRole, ReviewerInput


class ReviewAgent:
    """
    Final Code-Review Agent.
    Strictly read-only evaluation agent that reviews code changes across 12 criteria.
    Uses versioned PromptManager to load prompts and validate outputs.
    """

    def __init__(
        self,
        provider: AIProviderInterface,
        sandbox: SandboxInterface,
        sandbox_id: str,
        prompt_manager: Optional[PromptManager] = None,
    ):
        self.provider = provider
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id
        self.prompt_manager = prompt_manager or get_prompt_manager()

    async def _gather_review_context(
        self,
        requirement: str = "",
        plan: Optional[str] = None,
        test_results: Optional[str] = None,
        modified_files: Optional[List[str]] = None,
    ) -> str:
        """Read-only gathering of workspace status, git diff, file contents, and test outputs."""
        context_parts = []

        if requirement:
            context_parts.append(f"=== Task Requirement ===\n{requirement}")

        if plan:
            context_parts.append(f"=== Implementation Plan ===\n{plan}")

        if test_results:
            context_parts.append(f"=== Test Execution Results ===\n{test_results}")

        # Git status and diff
        try:
            diff_res = await self.sandbox.execute_command(self.sandbox_id, "git status; git diff")
            diff_text = diff_res.stdout if diff_res.exit_code == 0 else "No git repository active"
            context_parts.append(f"=== Git Status & Diff Summary ===\n{diff_text}")
        except Exception as e:
            logger.warning("Could not execute git diff for review context", error=str(e))
            context_parts.append("=== Git Status & Diff Summary ===\nNo git diff available.")

        # Read modified file contents (read-only)
        files_to_read = set(modified_files or [])
        if files_to_read:
            context_parts.append("=== Modified File Contents ===")
            for file_path in sorted(files_to_read):
                try:
                    content = await self.sandbox.read_file(self.sandbox_id, file_path)
                    preview = content[:5000] + ("\n... [truncated]" if len(content) > 5000 else "")
                    context_parts.append(f"--- File: {file_path} ---\n{preview}")
                except Exception as e:
                    context_parts.append(f"--- File: {file_path} (Could not read: {str(e)}) ---")

        return "\n\n".join(context_parts)

    async def review_final_code_structured(
        self,
        requirement: str = "",
        plan: Optional[str] = None,
        test_results: Optional[str] = None,
        modified_files: Optional[List[str]] = None,
        run_id: Optional[str] = None,
    ) -> ReviewResult:
        """
        Executes structured final code review across all 12 categories and 5 severities.
        Strictly read-only: does not modify code files.
        """
        logger.info("Running Final Code Review Agent (Structured)")

        context_text = await self._gather_review_context(
            requirement=requirement,
            plan=plan,
            test_results=test_results,
            modified_files=modified_files,
        )

        inputs = ReviewerInput(
            requirement=requirement,
            plan=plan,
            diff_summary=context_text,
            modified_files=modified_files or [],
            test_results=test_results,
        )

        rendered_prompt, metadata = self.prompt_manager.render_prompt(
            role=PromptRole.REVIEWER,
            inputs=inputs,
            user_or_task_id=run_id,
        )

        messages = [
            LLMMessage(role="system", content="You are a principal engineer and senior security reviewer performing a strict final code review."),
            LLMMessage(role="user", content=rendered_prompt),
        ]

        response = await self.provider.generate_response(messages=messages, temperature=0.1)
        content = response.content or ""

        if run_id:
            self.prompt_manager.audit_prompt_execution(run_id=run_id, metadata=metadata)

        return self._parse_review_response(content)

    def _parse_review_response(self, content: str) -> ReviewResult:
        """Parse LLM output into structured ReviewResult, fallback safely if unstructured."""
        try:
            # Clean markdown codeblocks if present
            json_str = content
            if "```" in content:
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
                if match:
                    json_str = match.group(1)
                else:
                    # Try finding raw json object braces
                    start = content.find("{")
                    end = content.rfind("}")
                    if start != -1 and end != -1:
                        json_str = content[start:end+1]

            data = json.loads(json_str)

            passed = bool(data.get("passed", True))
            summary = str(data.get("summary", "Final code review completed."))
            raw_findings = data.get("findings", [])

            findings: List[ReviewFinding] = []
            for item in raw_findings:
                sev_str = str(item.get("severity", "MEDIUM")).upper()
                try:
                    severity = ReviewSeverity(sev_str)
                except ValueError:
                    severity = ReviewSeverity.MEDIUM

                cat_str = str(item.get("category", "code_quality")).lower().replace(" ", "_")
                try:
                    category = ReviewCategory(cat_str)
                except ValueError:
                    category = ReviewCategory.CODE_QUALITY

                finding = ReviewFinding(
                    finding=str(item.get("finding", "Unspecified Finding")),
                    severity=severity,
                    affected_file=str(item.get("affected_file", "unknown")),
                    explanation=str(item.get("explanation", "")),
                    recommended_fix=str(item.get("recommended_fix", "")),
                    category=category,
                )
                findings.append(finding)

            return ReviewResult(
                passed=passed,
                summary=summary,
                findings=findings,
                categories_evaluated=list(ALL_REVIEW_CATEGORIES),
            )

        except Exception as e:
            logger.warning("Could not parse LLM review output as JSON. Using fallback parser.", error=str(e))
            # Fallback for plain text response
            passed = "CRITICAL" not in content and "HIGH" not in content and "FAIL" not in content.upper()
            return ReviewResult(
                passed=passed,
                summary=content[:300] if content else "Completed unstructured review.",
                findings=[],
                categories_evaluated=list(ALL_REVIEW_CATEGORIES),
            )

    async def review_final_code(
        self,
        requirement: str = "",
        plan: Optional[str] = None,
        test_results: Optional[str] = None,
        modified_files: Optional[List[str]] = None,
    ) -> str:
        """Backwards compatible review method returning markdown report string."""
        result = await self.review_final_code_structured(
            requirement=requirement,
            plan=plan,
            test_results=test_results,
            modified_files=modified_files,
        )
        return result.to_markdown()
