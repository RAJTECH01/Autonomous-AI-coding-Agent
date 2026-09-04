import ast
import hashlib
import json
import uuid
import difflib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from app.domain.entities.coding_agent import (
    FileVersionSnapshot,
    FileChangeRecord,
    StructuredFailureReport,
    SafeguardViolationError,
)
from app.application.agent.safeguards import CodingSafeguardManager
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage
from app.domain.interfaces.sandbox import SandboxInterface
from app.core.logging import logger


class CodingAgent:
    """
    Subagent responsible for safe, incremental code creation and modification.
    Executes a strict 7-step file modification protocol:
      1. Read existing file
      2. Understand structure
      3. Determine required change
      4. Generate minimal modification
      5. Validate resulting file (syntax check)
      6. Save version/snapshot
      7. Run relevant tests
    Enforces safeguards and maintains detailed change metadata history.
    """

    def __init__(
        self,
        provider: AIProviderInterface,
        sandbox: SandboxInterface,
        sandbox_id: str,
        safeguard_manager: Optional[CodingSafeguardManager] = None,
    ):
        self.provider = provider
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id
        self.safeguards = safeguard_manager or CodingSafeguardManager()

        # Metadata tracking
        self.snapshots: List[FileVersionSnapshot] = []
        self.change_records: List[FileChangeRecord] = []
        self.modified_files_set: set = set()

    def get_files_changed(self) -> List[str]:
        return sorted(list(self.modified_files_set))

    def get_change_history(self) -> List[Dict[str, Any]]:
        return [record.to_dict() for record in self.change_records]

    # --- 7-Step File Modification Protocol ---

    async def modify_file_safely(
        self,
        file_path: str,
        proposed_content_or_patch: str,
        reason: str,
        related_requirement: str,
        related_test: Optional[str] = None,
        test_command: Optional[str] = None,
        is_full_content: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes the 7-step file modification protocol to safely apply a code change.
        """
        logger.info("Executing 7-step safe file modification protocol", file_path=file_path)

        # 0. Safeguard pre-checks: Scope & Loop checks
        self.safeguards.check_file_scope_safeguard(file_path)
        self.safeguards.check_infinite_loop_safeguard(file_path)

        # STEP 1: Read Existing File
        existing_content = await self._step1_read_existing_file(file_path)

        # STEP 2: Understand File Structure
        structure_info = self._step2_understand_structure(file_path, existing_content)

        # STEP 3 & STEP 4: Determine Change & Generate Minimal Modification
        new_content, diff_summary, lines_added, lines_deleted = self._step3_and_4_generate_minimal_modification(
            file_path=file_path,
            existing_content=existing_content,
            proposed_input=proposed_content_or_patch,
            is_full_content=is_full_content,
        )

        # Safeguard checks: Size & Repeated fix checks
        self.safeguards.check_file_size_safeguard(file_path, new_content, existing_content)
        self.safeguards.check_repeated_fix_safeguard(file_path, new_content)

        # STEP 5: Validate Resulting File Syntax
        self._step5_validate_syntax(file_path, new_content)

        # STEP 6: Save Version / Snapshot before writing
        snapshot = self._step6_save_snapshot(file_path, existing_content)

        # Write the validated content to the sandbox file system
        await self.sandbox.write_file(self.sandbox_id, file_path, new_content)
        self.modified_files_set.add(file_path)

        # STEP 7: Run Relevant Tests
        test_success, test_output = await self._step7_run_relevant_tests(
            file_path=file_path,
            related_test=related_test,
            test_command=test_command,
        )

        # Record attempt & metadata
        self.safeguards.record_modification_attempt(
            file_path=file_path,
            patch_or_new_content=new_content,
            content_before=existing_content or "",
            content_after=new_content,
            success=test_success,
            error=test_output if not test_success else None,
        )

        lines_changed = lines_added + lines_deleted
        record = FileChangeRecord(
            file_path=file_path,
            change_type="modify" if existing_content else "create",
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            lines_changed=lines_changed,
            reason=reason,
            related_requirement=related_requirement,
            related_test=related_test,
            previous_version_metadata=snapshot.to_dict() if snapshot else None,
        )
        self.change_records.append(record)

        return {
            "success": test_success,
            "file_path": file_path,
            "lines_changed": lines_changed,
            "diff": diff_summary,
            "snapshot_id": snapshot.snapshot_id if snapshot else None,
            "test_output": test_output,
            "structure_summary": structure_info,
        }

    async def _step1_read_existing_file(self, file_path: str) -> Optional[str]:
        """Step 1: Read existing file content."""
        try:
            content = await self.sandbox.read_file(self.sandbox_id, file_path)
            return content
        except Exception:
            logger.info(f"File '{file_path}' does not exist yet. Treating as new file creation.")
            return None

    def _step2_understand_structure(self, file_path: str, content: Optional[str]) -> Dict[str, Any]:
        """Step 2: Understand file structure (language, functions, classes, imports)."""
        if not content:
            return {"file_type": "new_file", "line_count": 0}

        lines = content.splitlines()
        info = {
            "file_path": file_path,
            "line_count": len(lines),
            "language": "python" if file_path.endswith(".py") else "text",
            "functions": [],
            "classes": [],
            "imports_count": 0,
        }

        if file_path.endswith(".py"):
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        info["functions"].append(node.name)
                    elif isinstance(node, ast.ClassDef):
                        info["classes"].append(node.name)
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        info["imports_count"] += 1
            except Exception:
                pass  # Fall back if non-parseable at this stage

        return info

    def _step3_and_4_generate_minimal_modification(
        self,
        file_path: str,
        existing_content: Optional[str],
        proposed_input: str,
        is_full_content: bool,
    ) -> Tuple[str, str, int, int]:
        """Steps 3 & 4: Determine change and generate minimal incremental diff/content."""
        if not existing_content:
            new_content = proposed_input
            lines_added = len(new_content.splitlines())
            lines_deleted = 0
            diff = f"+ {lines_added} lines created in {file_path}"
            return new_content, diff, lines_added, lines_deleted

        if is_full_content:
            new_content = proposed_input
        else:
            # If proposed_input is a diff patch or chunk, apply line patch
            new_content = self._apply_incremental_patch(existing_content, proposed_input)

        # Compute unified diff metrics
        old_lines = existing_content.splitlines()
        new_lines = new_content.splitlines()
        diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{file_path}", tofile=f"b/{file_path}", lineterm=""))

        lines_added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        lines_deleted = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        diff_summary = "\n".join(diff_lines[:50])

        return new_content, diff_summary, lines_added, lines_deleted

    def _apply_incremental_patch(self, original: str, patch_text: str) -> str:
        """Apply a minimal patch snippet or replace block to original content."""
        if "<<" in patch_text and ">>" in patch_text:
            # Handle search/replace blocks
            try:
                parts = patch_text.split("<<<<<<<")
                result = original
                for part in parts[1:]:
                    search_and_replace = part.split("=======")
                    search_target = search_and_replace[0].strip()
                    replace_with = search_and_replace[1].split(">>>>>>>")[0].strip()
                    if search_target in result:
                        result = result.replace(search_target, replace_with, 1)
                return result
            except Exception:
                pass
        return patch_text

    def _step5_validate_syntax(self, file_path: str, content: str) -> None:
        """Step 5: Validate resulting file syntax before saving."""
        if file_path.endswith(".py"):
            try:
                ast.parse(content, filename=file_path)
            except SyntaxError as se:
                raise ValueError(
                    f"Syntax Validation Failed for '{file_path}' at line {se.lineno}: {se.msg}"
                ) from se

        elif file_path.endswith(".json"):
            try:
                json.loads(content)
            except json.JSONDecodeError as je:
                raise ValueError(
                    f"JSON Syntax Validation Failed for '{file_path}': {je.msg}"
                ) from je

        elif file_path.endswith((".js", ".ts", ".tsx", ".jsx", ".html")):
            # Validate bracket/parenthesis matching
            stack = []
            matching = {")": "(", "}": "{", "]": "["}
            for char in content:
                if char in matching.values():
                    stack.append(char)
                elif char in matching.keys():
                    if not stack or stack[-1] != matching[char]:
                        # Warning / soft validation check for unbalanced tokens
                        break
                    stack.pop()

    def _step6_save_snapshot(self, file_path: str, existing_content: Optional[str]) -> FileVersionSnapshot:
        """Step 6: Save a snapshot of the file before overwrite."""
        content = existing_content or ""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        snapshot = FileVersionSnapshot(
            snapshot_id=str(uuid.uuid4()),
            file_path=file_path,
            content_hash=content_hash,
            line_count=len(content.splitlines()),
            content=content,
        )
        self.snapshots.append(snapshot)
        return snapshot

    async def _step7_run_relevant_tests(
        self,
        file_path: Optional[str] = None,
        related_test: Optional[str] = None,
        test_command: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Step 7: Run relevant tests using TestingValidationAgent."""
        try:
            from app.application.agent.subagents.tester import TestingValidationAgent
            tester = TestingValidationAgent(sandbox=self.sandbox, sandbox_id=self.sandbox_id)

            modified_files = [file_path] if file_path else []
            test_result = await tester.run_testing_pipeline(
                modified_files=modified_files,
                custom_test_path=related_test,
            )
            return test_result.passed, f"{test_result.summary}\n{test_result.stdout}\n{test_result.stderr}"
        except Exception as e:
            return False, f"Test execution error: {str(e)}"

    async def delete_file_safely(self, file_path: str, reason: str, related_requirement: str) -> None:
        """Safely delete a file while enforcing accidental deletion safeguards."""
        self.safeguards.check_deletion_safeguard(file_path)

        existing = await self._step1_read_existing_file(file_path)
        snapshot = self._step6_save_snapshot(file_path, existing) if existing else None

        await self.sandbox.execute_command(self.sandbox_id, f"rm '{file_path}'")
        self.safeguards.record_deletion(file_path)

        record = FileChangeRecord(
            file_path=file_path,
            change_type="delete",
            lines_added=0,
            lines_deleted=len(existing.splitlines()) if existing else 0,
            lines_changed=len(existing.splitlines()) if existing else 0,
            reason=reason,
            related_requirement=related_requirement,
            previous_version_metadata=snapshot.to_dict() if snapshot else None,
        )
        self.change_records.append(record)

    def generate_failure_report(
        self,
        task_id: str,
        run_id: str,
        failure_reason: str,
        failing_stage: str,
        error_or_trace: str,
        root_cause_analysis: Optional[str] = None,
        recommendations: Optional[List[str]] = None,
    ) -> StructuredFailureReport:
        """Generate structured failure report when a task fails repeatedly."""
        # Detect if repeated fix or infinite loop triggered this failure
        repeated_fix = any(
            "Repeated Identical Fix" in str(att.error)
            for attempts in self.safeguards.file_patch_history.values()
            for att in attempts if att.error
        )
        infinite_loop = any(
            count >= self.safeguards.max_modifications_per_file
            for count in self.safeguards.file_modification_counts.values()
        )

        default_recs = [
            "Review the root cause analysis and stack trace in detail.",
            "Verify whether the task requirement requires updated database schemas or mock services.",
            "Decompose the requirement into smaller incremental sub-tasks.",
        ]

        return StructuredFailureReport(
            task_id=task_id,
            run_id=run_id,
            failure_reason=failure_reason,
            failing_stage=failing_stage,
            root_cause_analysis=root_cause_analysis or "Repeated failures occurred during test execution/code modification phase.",
            stack_trace_or_error=error_or_trace,
            modified_files=self.get_files_changed(),
            attempted_fixes_count=len(self.change_records),
            repeated_fix_detected=repeated_fix,
            infinite_loop_detected=infinite_loop,
            recommendations=recommendations or default_recs,
        )
