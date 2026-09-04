import json
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from app.domain.entities.debugging_agent import (
    DebugInputContext,
    ValidationComparison,
    StructuredDebugResult,
)
from app.domain.entities.testing_agent import StructuredTestResult
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage
from app.domain.interfaces.sandbox import SandboxInterface
from app.application.agent.subagents.coder import CodingAgent
from app.application.agent.subagents.tester import TestingValidationAgent
from app.core.logging import logger

from app.core.prompts.manager import PromptManager, get_prompt_manager
from app.schemas.prompts import PromptRole, DebuggerInput, CoderInput

DEFAULT_MAX_DEBUG_LOOPS = 3


class DebuggingAgent:
    """
    Subagent responsible for automated root cause analysis, minimal fix generation,
    safe patch application via CodingAgent, real test verification via TestingValidationAgent,
    validation delta comparison, loop detection, and structured debug reporting.
    """
    __test__ = False

    def __init__(
        self,
        provider: AIProviderInterface,
        sandbox: SandboxInterface,
        sandbox_id: str,
        coder: Optional[CodingAgent] = None,
        tester: Optional[TestingValidationAgent] = None,
        max_debug_loops: int = DEFAULT_MAX_DEBUG_LOOPS,
        prompt_manager: Optional[PromptManager] = None,
    ):
        self.provider = provider
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id
        self.coder = coder or CodingAgent(provider=provider, sandbox=sandbox, sandbox_id=sandbox_id)
        self.tester = tester or TestingValidationAgent(sandbox=sandbox, sandbox_id=sandbox_id, provider=provider)
        self.max_debug_loops = max_debug_loops
        self.prompt_manager = prompt_manager or get_prompt_manager()

        # Loop detection history
        self.failure_fingerprints: Dict[str, int] = {}

    async def execute_debugging_flow(
        self,
        context: DebugInputContext,
    ) -> StructuredDebugResult:
        """
        Executes the 7-step debugging protocol:
          1. Identify failure
          2. Determine probable root cause
          3. Identify affected files
          4. Propose minimal fix
          5. Apply fix via approved coding tools
          6. Re-run relevant tests
          7. Compare new result with previous result
        """
        logger.info("Executing 7-step Debugging Agent flow")

        # 0. Loop Detection Check
        error_fingerprint = self._compute_error_fingerprint(context)
        loop_count = self.failure_fingerprints.get(error_fingerprint, 0) + 1
        self.failure_fingerprints[error_fingerprint] = loop_count

        if loop_count >= self.max_debug_loops:
            logger.warning("Debugging Loop Detected! Halting retries.", loop_count=loop_count)
            prev_failed = self._extract_failed_count(context.test_results)
            return StructuredDebugResult(
                root_cause=f"Infinite Debug Loop Detected: Same failure pattern occurred {loop_count} times without test resolution.",
                affected_files=context.changed_files,
                proposed_fix="Halt retries and request architectural clarification / manual review.",
                applied_changes=[],
                validation_result=ValidationComparison(
                    passed=False,
                    previous_failed_count=prev_failed,
                    current_failed_count=prev_failed,
                    tests_fixed_count=0,
                    new_regressions_count=0,
                    delta_summary="Loop detected: No progress achieved.",
                ),
                confidence=0.9,
                loop_detected=True,
            )

        # STEP 1 & 2: Identify Failure & Determine Probable Root Cause via LLM
        root_cause, affected_files, proposed_fix, confidence = await self._analyze_root_cause_and_plan(context)

        applied_changes: List[Dict[str, Any]] = []

        # STEP 3, 4 & 5: Apply Minimal Fix via CodingAgent
        if affected_files and proposed_fix:
            for file_path in affected_files:
                try:
                    # Read current file content to perform minimal fix
                    current_content = await self.coder._step1_read_existing_file(file_path)
                    if not current_content:
                        continue

                    # Generate fixed code using LLM minimal patch prompt
                    fixed_code = await self._generate_fixed_file_content(
                        file_path=file_path,
                        current_content=current_content,
                        root_cause=root_cause,
                        proposed_fix=proposed_fix,
                    )

                    mod_res = await self.coder.modify_file_safely(
                        file_path=file_path,
                        proposed_content_or_patch=fixed_code,
                        reason=f"Debug fix: {root_cause[:100]}",
                        related_requirement=context.requirement,
                    )

                    applied_changes.append({
                        "file_path": file_path,
                        "lines_changed": mod_res.get("lines_changed", 0),
                        "diff": mod_res.get("diff", ""),
                    })
                except Exception as e:
                    logger.error(f"Failed to apply debug fix to '{file_path}'", error=str(e))

        # STEP 6: Re-run Relevant Tests via TestingValidationAgent (NO invented results!)
        new_test_result: StructuredTestResult = await self.tester.run_testing_pipeline(
            modified_files=affected_files or context.changed_files
        )

        # STEP 7: Compare New Result with Previous Result
        comparison = self._compare_test_results(
            prev_results=context.test_results,
            new_results=new_test_result,
        )

        return StructuredDebugResult(
            root_cause=root_cause,
            affected_files=affected_files,
            proposed_fix=proposed_fix,
            applied_changes=applied_changes,
            validation_result=comparison,
            confidence=confidence,
            loop_detected=False,
        )

    def _compute_error_fingerprint(self, context: DebugInputContext) -> str:
        text = f"{context.runtime_errors or ''}\n{context.compiler_errors or ''}\n{context.logs or ''}\n{str(context.test_results or '')}"
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    async def _analyze_root_cause_and_plan(
        self,
        context: DebugInputContext,
    ) -> Tuple[str, List[str], str, float]:
        inputs = DebuggerInput(
            requirement=context.requirement,
            changed_files=context.changed_files,
            test_results=str(context.test_results) if context.test_results else None,
            error_logs=context.runtime_errors or context.compiler_errors or context.logs,
        )

        rendered_prompt, metadata = self.prompt_manager.render_prompt(
            role=PromptRole.DEBUGGER,
            inputs=inputs,
        )

        messages = [
            LLMMessage(role="system", content="You are a principal debugging specialist. Return only valid JSON."),
            LLMMessage(role="user", content=rendered_prompt),
        ]

        response = await self.provider.generate_response(messages=messages, temperature=0.1)

        try:
            structured = self.prompt_manager.parse_and_validate_output(
                role=PromptRole.DEBUGGER,
                llm_response_content=response.content,
            )
            return (
                structured.root_cause,
                structured.affected_files or context.changed_files,
                structured.proposed_fix,
                structured.confidence,
            )
        except Exception:
            logger.warning("Could not parse JSON response from debug analysis; using fallback extraction.")
            return (
                response.content[:300],
                context.changed_files,
                "Apply targeted debug fix",
                0.75,
            )

    async def _generate_fixed_file_content(
        self,
        file_path: str,
        current_content: str,
        root_cause: str,
        proposed_fix: str,
    ) -> str:
        inputs = CoderInput(
            requirement=f"Root cause: {root_cause}\nFix strategy: {proposed_fix}",
            file_path=file_path,
            language="python" if file_path.endswith(".py") else "text",
            existing_code=current_content,
        )

        rendered_prompt, metadata = self.prompt_manager.render_prompt(
            role=PromptRole.CODER,
            inputs=inputs,
        )

        messages = [
            LLMMessage(role="system", content="You are an expert code repair engine. Return only updated file code."),
            LLMMessage(role="user", content=rendered_prompt),
        ]

        res = await self.provider.generate_response(messages=messages, temperature=0.1)
        code = res.content.strip()

        try:
            structured = self.prompt_manager.parse_and_validate_output(
                role=PromptRole.CODER,
                llm_response_content=code,
            )
            code = structured.code_content
        except Exception:
            if code.startswith("```"):
                lines = code.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                code = "\n".join(lines)

        return code

    def _extract_failed_count(self, test_results: Optional[Any]) -> int:
        if not test_results:
            return 1
        if isinstance(test_results, StructuredTestResult):
            return test_results.failed_count
        if isinstance(test_results, dict):
            return test_results.get("failed_count", 1)
        return 1

    def _compare_test_results(
        self,
        prev_results: Optional[Any],
        new_results: StructuredTestResult,
    ) -> ValidationComparison:
        prev_failed = self._extract_failed_count(prev_results)
        curr_failed = new_results.failed_count

        tests_fixed = max(0, prev_failed - curr_failed)
        new_regressions = max(0, curr_failed - prev_failed)

        if new_results.passed:
            delta = f"SUCCESS: All tests passed ({tests_fixed} failing test(s) resolved)."
        elif tests_fixed > 0:
            delta = f"PARTIAL PROGRESS: Resolved {tests_fixed} failing test(s), {curr_failed} test(s) still failing."
        elif new_regressions > 0:
            delta = f"REGRESSION: Introduced {new_regressions} new test failure(s)."
        else:
            delta = f"NO CHANGE: Same {curr_failed} test(s) failing."

        return ValidationComparison(
            passed=new_results.passed,
            previous_failed_count=prev_failed,
            current_failed_count=curr_failed,
            tests_fixed_count=tests_fixed,
            new_regressions_count=new_regressions,
            delta_summary=delta,
        )
