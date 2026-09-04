import uuid
import json
import time
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pydantic import ValidationError

from app.domain.entities.agent import AgentRun, AgentLimits, ToolCall, ToolResult
from app.domain.entities.tool import (
    ToolPermission,
    ToolExecutionStatus,
    ToolAuditRecord,
    mask_sensitive_data,
)
from app.domain.interfaces.sandbox import SandboxInterface
from app.infrastructure.tools.registry import ToolRegistry
from app.infrastructure.tools.path_validator import PathSecurityError
from app.core.exceptions import ToolExecutionError, LimitExceededError
from app.core.logging import logger

BLOCKED_COMMAND_SUBSTRINGS = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",  # fork bomb
    "chmod 777 /",
    "shutdown",
    "reboot",
]

# Role-permission mapping for authorization check
ROLE_PERMISSIONS: Dict[str, List[ToolPermission]] = {
    "administrator": [ToolPermission.READ, ToolPermission.WRITE, ToolPermission.EXECUTE, ToolPermission.ADMIN],
    "project_owner": [ToolPermission.READ, ToolPermission.WRITE, ToolPermission.EXECUTE],
    "project_member": [ToolPermission.READ, ToolPermission.WRITE, ToolPermission.EXECUTE],
    "user": [ToolPermission.READ, ToolPermission.WRITE],
}


class ControlledToolLayer:
    """
    Controlled tool layer enforcing security boundaries, input validation, permission validation,
    command safety, timeouts, output limits, and secret-masked audit logging.
    """

    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry or ToolRegistry()
        self.audit_records: List[ToolAuditRecord] = []

    def validate_permission(
        self,
        tool_permission: ToolPermission,
        user_role: Optional[str] = None,
    ) -> None:
        """Enforce permission verification based on user role."""
        if not user_role:
            return  # Default internal agent execution authorized

        allowed_permissions = ROLE_PERMISSIONS.get(user_role, [ToolPermission.READ])
        if tool_permission not in allowed_permissions:
            raise ToolExecutionError(
                f"Permission denied: Role '{user_role}' does not have required '{tool_permission.value}' permission."
            )

    def validate_command_safety(self, tool_name: str, args: Dict[str, Any]) -> None:
        """Enforce safety rules so destructive commands are rejected."""
        if tool_name in ("execute_command", "run_command"):
            cmd = args.get("command", "")
            for blocked in BLOCKED_COMMAND_SUBSTRINGS:
                if blocked in cmd:
                    raise ToolExecutionError(
                        f"Command security violation: Forbidden command pattern '{blocked}' detected."
                    )

    async def execute_tool(
        self,
        sandbox: SandboxInterface,
        sandbox_id: str,
        tool_name: str,
        args: Dict[str, Any],
        run: AgentRun,
        step_id: Optional[str] = None,
        user_role: Optional[str] = None,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ToolResult:
        limits = run.limits
        start_dt = datetime.now(timezone.utc)
        start_time = time.time()
        call_id = str(uuid.uuid4())

        # 1. Enforce max tool calls limit
        if run.total_tool_calls >= limits.max_tool_calls:
            raise LimitExceededError(
                f"Limit exceeded: Maximum tool calls limit ({limits.max_tool_calls}) reached."
            )

        # 2. Tool Registry Lookup (Rejects unknown tools)
        tool = self.registry.get_tool(tool_name)

        # 3. Input Schema Validation
        try:
            tool.validate_inputs(args)
        except ValidationError as ve:
            raise ToolExecutionError(f"Tool input schema validation failed for '{tool_name}': {ve}")

        tool_call_obj = ToolCall(
            id=call_id,
            tool_name=tool_name,
            tool_input=mask_sensitive_data(args),
            step_id=step_id,
            created_at=start_dt,
        )

        execution_status = ToolExecutionStatus.SUCCESS
        error_msg: Optional[str] = None
        output = ""

        try:
            # 4. Permission Validation
            self.validate_permission(tool.permission_required, user_role)

            # 5. Command Safety Validation
            self.validate_command_safety(tool_name, args)

            # 6. Enforce max files changed limit for write operations
            if tool_name in ("write_file", "create_file", "edit_file"):
                file_path = args.get("path") or args.get("file_path")
                if file_path and file_path not in run.execution_summary.get("modified_files", []):
                    if run.files_changed_count >= limits.max_files_changed:
                        raise LimitExceededError(
                            f"Limit exceeded: Maximum files changed limit ({limits.max_files_changed}) reached."
                        )

            # 7. Timeout Enforcement
            timeout = min(tool.timeout_seconds, 120)
            raw_res = await asyncio.wait_for(
                tool.execute(sandbox, sandbox_id, **args),
                timeout=timeout,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 8. Output Length Capping
            output = raw_res.output or ""
            if len(output) > limits.max_generated_output:
                truncated_note = f"\n...[Output truncated: Exceeded max length of {limits.max_generated_output} chars]"
                output = output[: limits.max_generated_output] + truncated_note

            error_msg = raw_res.error or None
            if not raw_res.success:
                execution_status = ToolExecutionStatus.FAILED

            # Update run metrics
            run.total_tool_calls += 1
            run.total_output_chars += len(output)

            if tool_name in ("write_file", "create_file", "edit_file"):
                file_path = args.get("path") or args.get("file_path")
                if file_path:
                    modified = run.execution_summary.setdefault("modified_files", [])
                    if file_path not in modified:
                        modified.append(file_path)
                        run.files_changed_count = len(modified)

            result_obj = ToolResult(
                id=str(uuid.uuid4()),
                tool_call_id=call_id,
                stdout_summary=output[:500],
                stderr_summary=error_msg[:500] if error_msg else None,
                exit_code=raw_res.metadata.get("exit_code", 0) if raw_res.metadata else 0,
                execution_duration_ms=duration_ms,
                success=raw_res.success,
                output=output,
                error=error_msg,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            run.total_tool_calls += 1
            execution_status = ToolExecutionStatus.TIMEOUT
            error_msg = f"Tool '{tool_name}' timed out after {tool.timeout_seconds} seconds."
            logger.error("Tool execution timeout", tool_name=tool_name, timeout=tool.timeout_seconds)
            result_obj = ToolResult(
                id=str(uuid.uuid4()),
                tool_call_id=call_id,
                stdout_summary="",
                stderr_summary=error_msg,
                exit_code=124,
                execution_duration_ms=duration_ms,
                success=False,
                output="",
                error=error_msg,
            )

        except (PathSecurityError, ToolExecutionError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            run.total_tool_calls += 1
            execution_status = ToolExecutionStatus.DENIED
            error_msg = str(e)
            logger.warning("Tool execution security rejection", tool_name=tool_name, error=str(e))
            result_obj = ToolResult(
                id=str(uuid.uuid4()),
                tool_call_id=call_id,
                stdout_summary="",
                stderr_summary=error_msg[:500],
                exit_code=1,
                execution_duration_ms=duration_ms,
                success=False,
                output="",
                error=error_msg,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            run.total_tool_calls += 1
            execution_status = ToolExecutionStatus.FAILED
            error_msg = str(e)
            logger.error("Tool execution internal failure", tool_name=tool_name, error=str(e))
            result_obj = ToolResult(
                id=str(uuid.uuid4()),
                tool_call_id=call_id,
                stdout_summary="",
                stderr_summary=error_msg[:500],
                exit_code=1,
                execution_duration_ms=duration_ms,
                success=False,
                output="",
                error=error_msg,
            )

        end_dt = datetime.now(timezone.utc)

        # Instrument Production Metrics Registry
        from app.core.metrics import metrics_registry
        from app.core.logging import set_tool_call_id
        set_tool_call_id(call_id)
        metrics_registry.record_tool_call(tool_name, success=result_obj.success)

        if tool_name == "run_tests" and not result_obj.success:
            metrics_registry.record_test_failure()

        if execution_status == ToolExecutionStatus.FAILED and "sandbox" in (error_msg or "").lower():
            metrics_registry.record_sandbox_failure("container_error")

        # 9. Secret-Masked Audit Record Generation
        audit = ToolAuditRecord(
            id=str(uuid.uuid4()),
            user_id=user_id or run.initiator_id,
            project_id=project_id,
            agent_run_id=run.id,
            tool_name=tool_name,
            permission_required=tool.permission_required,
            status=execution_status,
            input_metadata=mask_sensitive_data(args),
            output_metadata={"output_length": len(output), "summary": output[:200]},
            error_metadata={"error": error_msg} if error_msg else None,
            execution_duration_ms=int((time.time() - start_time) * 1000),
            start_time=start_dt,
            end_time=end_dt,
        )
        self.audit_records.append(audit)

        logger.info(
            "Tool execution logged",
            tool_name=tool_name,
            status=execution_status.value,
            duration_ms=audit.execution_duration_ms,
            tool_call_id=call_id,
        )

        return result_obj
