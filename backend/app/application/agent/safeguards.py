import os
import hashlib
from typing import List, Dict, Set, Optional, Any
from app.domain.entities.coding_agent import SafeguardViolationError, PatchAttempt
from app.core.logging import logger

# List of critical project configuration files protected from accidental deletion
PROTECTED_PROJECT_FILES: Set[str] = {
    ".git",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    ".env",
    ".env.example",
    "alembic.ini",
    "Dockerfile",
    "docker-compose.yml",
    "pyproject.toml",
    "setup.py",
    "pytest.ini",
    "tsconfig.json",
}

DEFAULT_MAX_FILE_LINES = 2000
DEFAULT_MAX_FILE_BYTES = 200_000
DEFAULT_MAX_MODIFICATIONS_PER_FILE = 5
DEFAULT_MAX_DELETIONS_PER_RUN = 3


class CodingSafeguardManager:
    """
    Manager enforcing safety constraints on code modification operations.
    Safeguards against accidental deletion, unrelated file edits, huge files,
    infinite loops, and repeated identical fixes.
    """

    def __init__(
        self,
        allowed_target_files: Optional[List[str]] = None,
        max_file_lines: int = DEFAULT_MAX_FILE_LINES,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_modifications_per_file: int = DEFAULT_MAX_MODIFICATIONS_PER_FILE,
        max_deletions_per_run: int = DEFAULT_MAX_DELETIONS_PER_RUN,
    ):
        self.allowed_target_files = set(allowed_target_files) if allowed_target_files else None
        self.max_file_lines = max_file_lines
        self.max_file_bytes = max_file_bytes
        self.max_modifications_per_file = max_modifications_per_file
        self.max_deletions_per_run = max_deletions_per_run

        self.file_modification_counts: Dict[str, int] = {}
        self.file_patch_history: Dict[str, List[PatchAttempt]] = {}
        self.deletions_count: int = 0

    def check_deletion_safeguard(self, file_path: str) -> None:
        """1. Accidental Deletion Safeguard."""
        basename = os.path.basename(file_path).lower()
        if basename in PROTECTED_PROJECT_FILES or file_path in PROTECTED_PROJECT_FILES:
            raise SafeguardViolationError(
                f"Accidental Deletion Blocked: File '{file_path}' is a protected critical project file."
            )

        if self.deletions_count >= self.max_deletions_per_run:
            raise SafeguardViolationError(
                f"Accidental Deletion Blocked: Exceeded max file deletions limit ({self.max_deletions_per_run}) per run."
            )

    def record_deletion(self, file_path: str) -> None:
        self.deletions_count += 1

    def check_file_scope_safeguard(self, file_path: str) -> None:
        """2. Unrelated File Modification Safeguard."""
        normalized = os.path.normpath(file_path).replace("\\", "/")

        # Disallow editing system paths or parent directory traversal outside project root
        if normalized.startswith("..") or os.path.isabs(normalized) and not normalized.startswith("."):
            # Check if it attempts to break out of workspace
            if ".." in normalized.split("/"):
                raise SafeguardViolationError(
                    f"Unrelated File Modification Blocked: Path '{file_path}' attempts path traversal outside workspace."
                )

        # If explicit target list was provided by plan, restrict edits to allowed targets
        if self.allowed_target_files:
            clean_allowed = {os.path.normpath(f).replace("\\", "/") for f in self.allowed_target_files}
            if normalized not in clean_allowed:
                raise SafeguardViolationError(
                    f"Unrelated File Modification Blocked: File '{file_path}' is not in the approved plan targets: {sorted(list(clean_allowed))}."
                )

    def check_file_size_safeguard(
        self,
        file_path: str,
        new_content: str,
        existing_content: Optional[str] = None,
    ) -> None:
        """3. Huge Generated Files Safeguard."""
        line_count = len(new_content.splitlines())
        byte_count = len(new_content.encode("utf-8"))

        if line_count > self.max_file_lines:
            raise SafeguardViolationError(
                f"Huge File Blocked: Generated file '{file_path}' contains {line_count} lines (exceeds max threshold of {self.max_file_lines} lines)."
            )

        if byte_count > self.max_file_bytes:
            raise SafeguardViolationError(
                f"Huge File Blocked: Generated file '{file_path}' size is {byte_count} bytes (exceeds max threshold of {self.max_file_bytes} bytes)."
            )

        # Check for unapproved full-file expansion (>5x growth & >300 new lines)
        if existing_content and len(existing_content.strip()) > 0:
            old_lines = len(existing_content.splitlines())
            if old_lines > 20 and line_count > old_lines * 5 and (line_count - old_lines) > 300:
                raise SafeguardViolationError(
                    f"Huge File Blocked: File '{file_path}' expanded excessively from {old_lines} to {line_count} lines without incremental patching."
                )

    def check_infinite_loop_safeguard(self, file_path: str) -> None:
        """4. Infinite Modification Loop Safeguard."""
        current_count = self.file_modification_counts.get(file_path, 0)
        if current_count >= self.max_modifications_per_file:
            raise SafeguardViolationError(
                f"Infinite Loop Blocked: File '{file_path}' has been modified {current_count} times in this run without passing verification."
            )

    def check_repeated_fix_safeguard(self, file_path: str, patch_or_new_content: str) -> None:
        """5. Repeated Identical Fixes Safeguard."""
        content_hash = hashlib.sha256(patch_or_new_content.strip().encode("utf-8")).hexdigest()
        history = self.file_patch_history.get(file_path, [])

        for past_attempt in history:
            if not past_attempt.success and past_attempt.patch_hash == content_hash:
                raise SafeguardViolationError(
                    f"Repeated Identical Fix Blocked: Patch/content for '{file_path}' is identical to a previously failed attempt."
                )

    def record_modification_attempt(
        self,
        file_path: str,
        patch_or_new_content: str,
        content_before: str,
        content_after: str,
        success: bool,
        error: Optional[str] = None,
        iteration: int = 1,
    ) -> None:
        """Track modification count and patch history for loop & repeated fix detection."""
        self.file_modification_counts[file_path] = self.file_modification_counts.get(file_path, 0) + 1

        content_hash = hashlib.sha256(patch_or_new_content.strip().encode("utf-8")).hexdigest()
        hash_before = hashlib.sha256(content_before.encode("utf-8")).hexdigest()
        hash_after = hashlib.sha256(content_after.encode("utf-8")).hexdigest()

        attempt = PatchAttempt(
            file_path=file_path,
            patch_hash=content_hash,
            content_hash_before=hash_before,
            content_hash_after=hash_after,
            success=success,
            error=error,
            iteration=iteration,
        )

        self.file_patch_history.setdefault(file_path, []).append(attempt)
