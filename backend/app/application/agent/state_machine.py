import hashlib
import json
import time
import uuid
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.domain.entities.agent import (
    AgentState,
    AgentRun,
    AgentStep,
    AgentContext,
    AgentPlan,
    AgentLimits,
    ToolCall,
    ToolResult,
    AgentError,
)
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage
from app.domain.interfaces.sandbox import SandboxInterface
from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer
from app.infrastructure.tools.registry import ToolRegistry
from app.infrastructure.db.repositories.agent_repository import AgentRepository
from app.application.agent.memory_manager import AgentMemoryManager
from app.application.agent.subagents.analyzer import RequirementAndProjectAnalyzer
from app.application.agent.subagents.planner import PlanningAgent
from app.application.agent.subagents.debugger import DebuggingAgent
from app.application.agent.subagents.reviewer import ReviewAgent
from app.application.agent.subagents.coder import CodingAgent
from app.application.agent.subagents.tester import TestingValidationAgent
from app.domain.entities.coding_agent import SafeguardViolationError
from app.domain.entities.debugging_agent import DebugInputContext
from app.core.exceptions import LimitExceededError, ToolExecutionError
from app.core.logging import logger

from app.domain.entities.human_approval import ExecutionMode, ApprovalAction, HighRiskCategory
from app.core.approval.policy_engine import ApprovalPolicyEngine

SYSTEM_PROMPT = """You are an expert autonomous coding agent operating within an architecture pipeline.
Your objective is to generate and modify source code, create project files, run commands/tests, inspect errors, and complete requirements.
All actions must be performed through tool calls.
"""


class AgentStateMachine:
    """
    Autonomous Coding Agent implemented as a controlled state machine.
    Replaces uncontrolled while-loops with explicit, persisted state transitions,
    controlled tool execution, limit enforcement, and clean provider abstractions.
    """

    def __init__(
        self,
        task_id: str,
        user_prompt: str,
        provider: AIProviderInterface,
        sandbox: SandboxInterface,
        sandbox_id: str,
        repository: Optional[AgentRepository] = None,
        tool_registry: Optional[ToolRegistry] = None,
        limits: Optional[AgentLimits] = None,
        auto_approve: bool = True,
        execution_mode: Optional[ExecutionMode] = None,
        initiator_id: Optional[str] = None,
        provider_name: str = "anthropic",
        model_name: str = "claude-3-5-sonnet-20241022",
    ):
        self.limits = limits or AgentLimits()
        
        if execution_mode is None:
            execution_mode = ExecutionMode.AUTONOMOUS if auto_approve else ExecutionMode.APPROVAL_REQUIRED
        elif isinstance(execution_mode, str):
            execution_mode = ExecutionMode(execution_mode)

        self.execution_mode = execution_mode
        self.auto_approve = auto_approve if execution_mode == ExecutionMode.AUTONOMOUS else False

        self.run = AgentRun(
            id=str(uuid.uuid4()),
            task_id=task_id,
            state=AgentState.RECEIVED,
            execution_mode=self.execution_mode,
            initiator_id=initiator_id,
            provider_name=provider_name,
            model_name=model_name,
            limits=self.limits,
            started_at=datetime.now(timezone.utc),
        )

        self.context = AgentContext(
            user_prompt=user_prompt,
            project_id=task_id,
            task_id=task_id,
        )

        self.provider = provider
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id
        self.repository = repository
        self.policy_engine = ApprovalPolicyEngine()

        self.tool_layer = ControlledToolLayer(registry=tool_registry)
        self.memory = AgentMemoryManager()
        self.memory.set_system_prompt(SYSTEM_PROMPT)

        self.analyzer = RequirementAndProjectAnalyzer(provider, sandbox, sandbox_id)
        self.planner = PlanningAgent(provider)
        self.reviewer = ReviewAgent(provider, sandbox, sandbox_id)
        self.coder = CodingAgent(provider, sandbox, sandbox_id)
        self.tester = TestingValidationAgent(sandbox, sandbox_id, provider)
        self.debugger = DebuggingAgent(provider, sandbox, sandbox_id, coder=self.coder, tester=self.tester)

        self.step_counter = 0
        self.start_time = time.time()

    async def _persist_run(self) -> None:
        if self.repository:
            try:
                await self.repository.create_run(self.run)
            except Exception as e:
                logger.warning("Could not persist initial AgentRun to database", error=str(e))

    async def _transition_to(self, new_state: AgentState, thought_process: Optional[Dict[str, Any]] = None) -> None:
        old_state = self.run.state
        self.run.state = new_state
        self.step_counter += 1

        thought = thought_process or {"message": f"Transition from {old_state.value} to {new_state.value}"}
        step = AgentStep(
            id=str(uuid.uuid4()),
            run_id=self.run.id,
            step_number=self.step_counter,
            from_state=old_state,
            to_state=new_state,
            step_type=new_state.value.lower(),
            thought_process=thought,
            created_at=datetime.now(timezone.utc),
        )
        self.context.execution_history.append(step)

        logger.info(
            "Agent State Transition",
            run_id=self.run.id,
            from_state=old_state.value,
            to_state=new_state.value,
            step_number=self.step_counter,
        )

        if self.repository:
            try:
                await self.repository.create_step(step)
                await self.repository.update_run_state(self.run)
            except Exception as e:
                logger.warning("Failed to persist state transition to database", error=str(e))

    def _check_limits(self) -> None:
        elapsed = time.time() - self.start_time
        if elapsed > self.limits.max_execution_time:
            raise LimitExceededError(
                f"Execution timeout: Exceeded max execution time ({self.limits.max_execution_time}s)."
            )
        if self.run.current_iteration >= self.limits.max_iterations:
            raise LimitExceededError(
                f"Iteration limit reached: Exceeded max iterations ({self.limits.max_iterations})."
            )
        if self.run.total_tool_calls >= self.limits.max_tool_calls:
            raise LimitExceededError(
                f"Tool calls limit reached: Exceeded max tool calls ({self.limits.max_tool_calls})."
            )
        if self.run.files_changed_count >= self.limits.max_files_changed:
            raise LimitExceededError(
                f"File modification limit reached: Exceeded max files changed ({self.limits.max_files_changed})."
            )
        if self.run.total_output_chars >= self.limits.max_generated_output:
            raise LimitExceededError(
                f"Output limit reached: Exceeded max generated output ({self.limits.max_generated_output} chars)."
            )
        if self.run.review_attempts_count >= self.limits.max_review_attempts:
            raise LimitExceededError(
                f"Review attempt limit reached: Exceeded max review attempts ({self.limits.max_review_attempts})."
            )

    async def run_autonomous_loop(self) -> Dict[str, Any]:
        """Execute the agent state machine workflow through explicit state transitions."""
        await self._persist_run()

        from app.core.logging import set_run_id
        from app.core.metrics import metrics_registry
        set_run_id(self.run.id)
        metrics_registry.record_task_started()
        loop_start_time = time.time()

        try:
            # Git State Initialization & Branch Isolation
            from app.infrastructure.vcs.local_git_provider import LocalGitProvider
            git_provider = LocalGitProvider(sandbox=self.sandbox, sandbox_id=self.sandbox_id)
            
            try:
                initial_git_state = await git_provider.get_current_state(workspace_path="")
                logger.info("Recorded initial Git state", branch=initial_git_state.branch_name, commit=initial_git_state.commit_hash[:7])
                
                # If on protected or default branch, create isolated task branch
                if git_provider.is_protected_branch(initial_git_state.branch_name):
                    clean_task_id = re.sub(r'[^a-zA-Z0-9_-]', '-', self.run.task_id)
                    isolated_branch = f"agent/task-{clean_task_id[:18]}"
                    branch_res = await git_provider.create_branch(workspace_path="", branch_name=isolated_branch, checkout=True)
                    logger.info("Created isolated task branch", branch=branch_res.branch_name, success=branch_res.success)
            except Exception as e:
                logger.warning("Could not initialize Git workspace branch isolation", error=str(e))

            # 1. State: RECEIVED -> ANALYZING
            self._check_limits()
            await self._transition_to(AgentState.ANALYZING, {"action": "Loading project context and analyzing requirements"})
            analysis_res = await self.analyzer.analyze(self.context.user_prompt, run_id=self.run.id)
            analysis_text = analysis_res.get("analysis", "")
            file_tree = analysis_res.get("file_tree", "")

            # 2. State: ANALYZING -> PLANNING
            self._check_limits()
            await self._transition_to(AgentState.PLANNING, {"action": "Generating structured implementation plan"})
            plan_markdown = await self.planner.create_plan(self.context.user_prompt, analysis_text, file_tree=file_tree, run_id=self.run.id)
            
            plan_obj = AgentPlan(
                id=str(uuid.uuid4()),
                run_id=self.run.id,
                goals_summary=analysis_text[:300],
                plan_markdown=plan_markdown,
                version=1,
                status="active",
                created_at=datetime.now(timezone.utc),
            )
            self.context.active_plan = plan_obj
            if self.repository:
                try:
                    await self.repository.create_plan(plan_obj)
                except Exception as e:
                    logger.warning("Failed to persist AgentPlan to database", error=str(e))

            # Evaluate plan with Approval Policy Engine for High-Risk actions
            policy_eval = self.policy_engine.evaluate_plan(plan_markdown, target_files=[])
            if policy_eval.is_high_risk:
                self.run.high_risk_flagged = True
                self.run.high_risk_triggers = policy_eval.explanations
                logger.warning(
                    "High-Risk Operations Flagged in Implementation Plan",
                    run_id=self.run.id,
                    categories=[c.value for c in policy_eval.flagged_categories],
                    explanations=policy_eval.explanations,
                )

            # 3. State: PLANNING -> AWAITING_APPROVAL
            await self._transition_to(AgentState.AWAITING_APPROVAL, {"action": "Awaiting plan approval"})

            # PLAN_ONLY mode stops after plan generation
            if self.execution_mode == ExecutionMode.PLAN_ONLY:
                logger.info("PLAN_ONLY mode: Plan generated successfully. Stopping before code modification.", run_id=self.run.id)
                await self._transition_to(AgentState.COMPLETED, {"action": "Plan generation completed in PLAN_ONLY mode"})
                self.run.execution_summary = {
                    "status": self.run.state.value,
                    "plan": plan_markdown,
                    "message": "Plan generated successfully in PLAN_ONLY mode.",
                }
                return self.run.execution_summary

            # Mandatory Pause in AWAITING_APPROVAL for APPROVAL_REQUIRED mode or High-Risk flag
            if self.execution_mode == ExecutionMode.APPROVAL_REQUIRED or self.run.high_risk_flagged:
                reason = "High-Risk Operation Mandatory Approval" if self.run.high_risk_flagged else "User Approval Required"
                logger.info(f"Run paused in AWAITING_APPROVAL state ({reason})", run_id=self.run.id)
                self.run.execution_summary = {
                    "status": self.run.state.value,
                    "plan": plan_markdown,
                    "high_risk_flagged": self.run.high_risk_flagged,
                    "high_risk_triggers": self.run.high_risk_triggers,
                    "message": f"Paused in AWAITING_APPROVAL ({reason})",
                }
                return self.run.execution_summary

            # 4. State: AWAITING_APPROVAL -> IMPLEMENTING
            await self._transition_to(AgentState.IMPLEMENTING, {"action": "Plan approved. Starting code implementation"})

            # Coding implementation loop within controlled limits
            done_implementing = False
            while not done_implementing:
                self.run.current_iteration += 1
                self._check_limits()

                t0 = time.time()
                llm_response = await self.provider.generate_response(
                    messages=self.memory.get_messages(),
                    tools=self.tool_layer.registry.get_openai_schemas(),
                    model=self.run.model_name,
                    temperature=0.2,
                )
                t_lat = time.time() - t0

                metrics_registry.record_model_call(
                    provider=self.run.provider_name,
                    model_name=self.run.model_name,
                    latency_seconds=t_lat,
                    prompt_tokens=llm_response.prompt_tokens,
                    completion_tokens=llm_response.completion_tokens,
                )

                self.run.prompt_tokens += llm_response.prompt_tokens
                self.run.completion_tokens += llm_response.completion_tokens
                self.run.total_tokens_used += llm_response.total_tokens

                if llm_response.content:
                    self.memory.add_assistant_message(llm_response.content, tool_calls=llm_response.tool_calls)

                if not llm_response.tool_calls:
                    done_implementing = True
                    break

                for tc in llm_response.tool_calls:
                    self._check_limits()
                    tool_name = tc["function"]["name"]
                    tool_args = tc["function"]["arguments"]
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_args = {}

                    current_step_id = self.context.execution_history[-1].id if self.context.execution_history else None
                    tool_result = await self.tool_layer.execute_tool(
                        sandbox=self.sandbox,
                        sandbox_id=self.sandbox_id,
                        tool_name=tool_name,
                        args=tool_args,
                        run=self.run,
                        step_id=current_step_id,
                    )

                    tool_call_obj = ToolCall(
                        id=tool_result.tool_call_id,
                        tool_name=tool_name,
                        tool_input=tool_args,
                        step_id=current_step_id,
                    )

                    if self.repository:
                        try:
                            await self.repository.create_tool_call_and_result(tool_call_obj, tool_result)
                        except Exception as e:
                            logger.warning("Failed to persist tool execution to database", error=str(e))

                    if tool_result.success:
                        self.memory.add_tool_response(tc["id"], tool_result.output)
                    else:
                        # Record tool execution failure
                        self.memory.add_tool_response(tc["id"], f"Tool Execution Failed: {tool_result.error}\nOutput: {tool_result.output}")

            # 5. State: IMPLEMENTING -> TESTING
            self._check_limits()
            await self._transition_to(AgentState.TESTING, {"action": "Executing test suite verification"})

            tests_passed = False
            while not tests_passed:
                self._check_limits()
                current_step_id = self.context.execution_history[-1].id if self.context.execution_history else None

                # Execute test runner via controlled tool layer
                test_result = await self.tool_layer.execute_tool(
                    sandbox=self.sandbox,
                    sandbox_id=self.sandbox_id,
                    tool_name="run_tests",
                    args={},
                    run=self.run,
                    step_id=current_step_id,
                )

                if test_result.success:
                    tests_passed = True
                else:
                    self.run.test_attempts_count += 1
                    if self.run.test_attempts_count >= self.limits.max_test_attempts:
                        raise LimitExceededError(
                            f"Max test attempts ({self.limits.max_test_attempts}) reached without passing tests."
                        )

                    # 6. State: TESTING -> DEBUGGING
                    await self._transition_to(
                        AgentState.DEBUGGING,
                        {"action": f"Test failure detected (Attempt {self.run.test_attempts_count}/{self.limits.max_test_attempts}). Analyzing errors"},
                    )

                    error_obj = AgentError(
                        id=str(uuid.uuid4()),
                        run_id=self.run.id,
                        error_type="TestFailure",
                        stack_trace=test_result.error or test_result.output,
                        category="code_error",
                        step_id=current_step_id,
                    )
                    if self.repository:
                        try:
                            await self.repository.create_error(error_obj)
                        except Exception as e:
                            logger.warning("Failed to persist AgentError to database", error=str(e))

                    debug_ctx = DebugInputContext(
                        requirement=self.context.user_prompt,
                        implementation_plan=self.context.active_plan.plan_markdown if self.context.active_plan else None,
                        changed_files=self.coder.get_files_changed(),
                        test_results=test_result.output,
                        runtime_errors=test_result.error,
                        logs=test_result.stdout_summary,
                    )
                    debug_res = await self.debugger.execute_debugging_flow(debug_ctx)

                    if debug_res.loop_detected:
                        raise LimitExceededError(
                            f"Infinite Debug Loop Detected! The same failure repeated {self.debugger.max_debug_loops} times without resolution."
                        )

                    self.memory.add_user_message(f"Debug Analysis & Repair Results:\nRoot Cause: {debug_res.root_cause}\nProposed Fix: {debug_res.proposed_fix}\nValidation: {debug_res.validation_result.delta_summary}")

                    # Transition back to IMPLEMENTING to apply fix
                    await self._transition_to(
                        AgentState.IMPLEMENTING,
                        {"action": "Applying debug fix recommendations"},
                    )

                    # Re-run LLM implementation step for fix
                    llm_response = await self.provider.generate_response(
                        messages=self.memory.get_messages(),
                        tools=self.tool_layer.registry.get_openai_schemas(),
                        model=self.run.model_name,
                        temperature=0.2,
                    )
                    if llm_response.tool_calls:
                        for tc in llm_response.tool_calls:
                            tool_name = tc["function"]["name"]
                            tool_args = tc["function"]["arguments"]
                            if isinstance(tool_args, str):
                                try:
                                    tool_args = json.loads(tool_args)
                                except json.JSONDecodeError:
                                    tool_args = {}
                            res = await self.tool_layer.execute_tool(
                                sandbox=self.sandbox,
                                sandbox_id=self.sandbox_id,
                                tool_name=tool_name,
                                args=tool_args,
                                run=self.run,
                                step_id=current_step_id,
                            )
                            self.memory.add_tool_response(tc["id"], res.output if res.success else res.error)

                    # Transition back to TESTING state to verify the fix
                    await self._transition_to(
                        AgentState.TESTING,
                        {"action": "Re-testing after debug fix"},
                    )

                    # Loop continues back to TESTING state check

            # 7. State: TESTING -> REVIEWING & Implementation Cycle Loop
            validation_passed = False
            review_text = ""
            review_result = None

            while not validation_passed:
                self._check_limits()
                await self._transition_to(
                    AgentState.REVIEWING,
                    {"action": f"Performing final code quality and security review (Attempt {self.run.review_attempts_count + 1})"}
                )

                last_test_output = test_result.output if 'test_result' in locals() and test_result else None
                review_result = await self.reviewer.review_final_code_structured(
                    requirement=self.context.user_prompt,
                    plan=self.context.active_plan.plan_markdown if self.context.active_plan else None,
                    test_results=last_test_output,
                    modified_files=self.coder.get_files_changed(),
                    run_id=self.run.id,
                )
                review_text = review_result.to_markdown()

                # Check required validation criteria: tests passed AND no blocking review findings
                if tests_passed and not review_result.requires_another_cycle:
                    validation_passed = True
                    break

                # Validation failed / another implementation cycle required
                self.run.review_attempts_count += 1
                if self.run.review_attempts_count >= self.limits.max_review_attempts:
                    raise LimitExceededError(
                        f"Max review attempts ({self.limits.max_review_attempts}) reached without passing code review validation criteria. Unresolved blocking findings count: {review_result.blocking_findings_count}."
                    )

                logger.info(
                    "Code review validation failed. Triggering another implementation cycle.",
                    run_id=self.run.id,
                    blocking_count=review_result.blocking_findings_count,
                    attempt=self.run.review_attempts_count,
                )

                # Feed review findings back to memory for the coding agent
                findings_feedback = [
                    f"Final Code Review Feedback (Cycle {self.run.review_attempts_count}):",
                    f"Summary: {review_result.summary}",
                    "Actionable Fixes Required:",
                ]
                for f in review_result.findings:
                    findings_feedback.append(
                        f"- [{f.severity.value if hasattr(f.severity, 'value') else f.severity}] in {f.affected_file}: {f.finding}\n"
                        f"  Explanation: {f.explanation}\n"
                        f"  Recommended Fix: {f.recommended_fix}"
                    )
                self.memory.add_user_message("\n".join(findings_feedback))

                # Transition back to IMPLEMENTING state to apply fix
                await self._transition_to(
                    AgentState.IMPLEMENTING,
                    {"action": f"Applying code review feedback (Attempt {self.run.review_attempts_count})"},
                )

                # Re-run LLM implementation step
                llm_response = await self.provider.generate_response(
                    messages=self.memory.get_messages(),
                    tools=self.tool_layer.registry.get_openai_schemas(),
                    model=self.run.model_name,
                    temperature=0.2,
                )

                self.run.prompt_tokens += llm_response.prompt_tokens
                self.run.completion_tokens += llm_response.completion_tokens
                self.run.total_tokens_used += llm_response.total_tokens

                if llm_response.content:
                    self.memory.add_assistant_message(llm_response.content, tool_calls=llm_response.tool_calls)

                current_step_id = self.context.execution_history[-1].id if self.context.execution_history else None
                if llm_response.tool_calls:
                    for tc in llm_response.tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = tc["function"]["arguments"]
                        if isinstance(tool_args, str):
                            try:
                                tool_args = json.loads(tool_args)
                            except json.JSONDecodeError:
                                tool_args = {}
                        res = await self.tool_layer.execute_tool(
                            sandbox=self.sandbox,
                            sandbox_id=self.sandbox_id,
                            tool_name=tool_name,
                            args=tool_args,
                            run=self.run,
                            step_id=current_step_id,
                        )
                        self.memory.add_tool_response(tc["id"], res.output if res.success else res.error)

                # Re-run tests after implementation fix
                await self._transition_to(
                    AgentState.TESTING,
                    {"action": "Re-testing after review fix cycle"},
                )

                test_result = await self.tool_layer.execute_tool(
                    sandbox=self.sandbox,
                    sandbox_id=self.sandbox_id,
                    tool_name="run_tests",
                    args={},
                    run=self.run,
                    step_id=current_step_id,
                )
                tests_passed = test_result.success

            # 8. State: REVIEWING -> COMPLETED (Only when required validation criteria passed)
            self.run.completed_at = datetime.now(timezone.utc)
            await self._transition_to(AgentState.COMPLETED, {"action": "Execution completed successfully. All validation criteria passed."})

            dur_sec = time.time() - loop_start_time
            metrics_registry.record_task_completed(duration_seconds=dur_sec, iterations=self.run.current_iteration)

            self.run.execution_summary = {
                "run_id": self.run.id,
                "status": self.run.state.value,
                "iterations": self.run.current_iteration,
                "total_tool_calls": self.run.total_tool_calls,
                "files_changed_count": self.run.files_changed_count,
                "test_attempts": self.run.test_attempts_count,
                "review_attempts": self.run.review_attempts_count,
                "total_tokens_used": self.run.total_tokens_used,
                "plan": plan_markdown,
                "final_review": review_text,
                "review_findings": [f.to_dict() for f in review_result.findings] if review_result else [],
            }
            return self.run.execution_summary

        except Exception as e:
            dur_sec = time.time() - loop_start_time
            metrics_registry.record_task_failed(duration_seconds=dur_sec, iterations=self.run.current_iteration)

            logger.error("Agent State Machine Execution Failed", run_id=self.run.id, error=str(e))
            self.run.completed_at = datetime.now(timezone.utc)
            await self._transition_to(AgentState.FAILED, {"error": str(e)})

            error_obj = AgentError(
                id=str(uuid.uuid4()),
                run_id=self.run.id,
                error_type=type(e).__name__,
                stack_trace=str(e),
                category="limit_exceeded" if isinstance(e, LimitExceededError) else "system_error",
            )
            if self.repository:
                try:
                    await self.repository.create_error(error_obj)
                except Exception as ex:
                    logger.warning("Failed to persist AgentError to database", error=str(ex))

            failure_report = self.coder.generate_failure_report(
                task_id=self.context.task_id,
                run_id=self.run.id,
                failure_reason=str(e),
                failing_stage=self.run.state.value,
                error_or_trace=str(e),
            )

            self.run.execution_summary = {
                "run_id": self.run.id,
                "status": self.run.state.value,
                "error": str(e),
                "iterations": self.run.current_iteration,
                "total_tool_calls": self.run.total_tool_calls,
                "failure_report": failure_report.to_markdown(),
                "failure_report_details": {
                    "task_id": failure_report.task_id,
                    "failure_reason": failure_report.failure_reason,
                    "failing_stage": failure_report.failing_stage,
                    "repeated_fix_detected": failure_report.repeated_fix_detected,
                    "infinite_loop_detected": failure_report.infinite_loop_detected,
                    "recommendations": failure_report.recommendations,
                },
            }
            return self.run.execution_summary

    async def handle_user_approval(
        self,
        approver_id: Optional[str] = None,
        approver_role: Optional[str] = None,
    ) -> None:
        """User approves implementation plan -> transition to IMPLEMENTING.

        The risk findings are preserved, not cleared: an approved high-risk run must
        stay identifiable as one afterwards. What approval records instead is *who*
        accepted *which* risks, so execution-time gating can check its authority
        (finding AUTHZ-04).
        """
        if self.run.state != AgentState.AWAITING_APPROVAL:
            raise ValueError(f"Cannot approve run in state {self.run.state.value}. Must be AWAITING_APPROVAL.")

        self.run.high_risk_approved = True
        self.run.approved_by = approver_id
        self.run.approved_at = datetime.now(timezone.utc)
        self.run.approved_plan_hash = (
            hashlib.sha256(self.context.active_plan.plan_markdown.encode("utf-8")).hexdigest()
            if self.context.active_plan else None
        )

        await self._transition_to(
            AgentState.IMPLEMENTING,
            {
                "action": "User approved implementation plan.",
                "approved_by": approver_id,
                "approver_role": approver_role,
                "high_risk_flagged": self.run.high_risk_flagged,
                "high_risk_triggers": self.run.high_risk_triggers,
            },
        )

    async def handle_user_rejection(self, feedback_notes: Optional[str] = None) -> None:
        """User rejects implementation plan -> transition back to PLANNING with feedback."""
        if self.run.state != AgentState.AWAITING_APPROVAL:
            raise ValueError(f"Cannot reject run in state {self.run.state.value}. Must be AWAITING_APPROVAL.")

        thought = {"action": "User rejected plan", "feedback_notes": feedback_notes}
        if feedback_notes:
            self.memory.add_user_message(f"User rejected plan with feedback: {feedback_notes}. Please revise the implementation plan.")
        
        await self._transition_to(AgentState.PLANNING, thought)

    async def handle_user_cancellation(self) -> None:
        """User cancels execution run -> transition to CANCELLED."""
        self.run.completed_at = datetime.now(timezone.utc)
        await self._transition_to(AgentState.CANCELLED, {"action": "Run cancelled by user decision."})

    async def handle_modify_requirements(self, new_requirement_prompt: str) -> None:
        """User updates requirement prompt -> reset context and transition to ANALYZING."""
        self.context.user_prompt = new_requirement_prompt
        self.memory.add_user_message(f"Requirement prompt updated by user: {new_requirement_prompt}. Re-analyzing requirements.")
        await self._transition_to(AgentState.ANALYZING, {"action": "Requirements prompt updated by user", "new_prompt": new_requirement_prompt})
