import os
from pathlib import Path, PurePosixPath, PureWindowsPath, PurePath
from typing import List, Optional
from app.core.exceptions import ToolExecutionError


class PathSecurityError(ToolExecutionError):
    """Raised when a path validation check fails due to security rules."""
    pass


BLOCKED_SYSTEM_PATH_SUBSTRINGS: List[str] = [
    "/etc/",
    "/etc",
    "/proc/",
    "/proc",
    "/sys/",
    "/sys",
    "/dev/",
    "/dev",
    "/var/",
    "/usr/",
    "/root",
    "c:\\windows",
    "c:/windows",
    "system32",
    "program files",
]

BLOCKED_SECRET_FILES: List[str] = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.staging",
    "id_rsa",
    "id_rsa.pub",
    "id_ed25519",
    "id_ed25519.pub",
    "credentials.json",
    "service_account.json",
    ".aws/credentials",
    ".git/config",
]

BLOCKED_SECRET_EXTENSIONS: List[str] = [
    ".pem",
    ".key",
    ".pfx",
    ".p12",
    ".crt",
    ".kdbx",
]


class PathValidator:
    """
    Validates filesystem paths against security boundaries, preventing path traversal,
    system directory access, secret/key file access, and cross-project access.
    """

    @staticmethod
    def validate_workspace_path(
        raw_path: str,
        workspace_root: str = "/workspace",
        allow_absolute: bool = False,
    ) -> str:
        """
        Validates and resolves a path relative to the given workspace root.
        
        Returns the sanitized relative path string within workspace root.
        Throws PathSecurityError if validation fails.
        """
        if not raw_path or not raw_path.strip():
            raise PathSecurityError("Path validation error: Empty path provided.")

        clean_path_str = raw_path.strip()

        # 1. Reject explicit path traversal constructs
        parts = clean_path_str.replace("\\", "/").split("/")
        if ".." in parts:
            raise PathSecurityError(f"Path traversal detected: '{raw_path}' contains parent directory '..' reference.")

        # 2. Check blocked system path substrings
        path_lower = clean_path_str.lower()
        for blocked_sys in BLOCKED_SYSTEM_PATH_SUBSTRINGS:
            if blocked_sys in path_lower:
                raise PathSecurityError(f"Security violation: Access to system path pattern '{blocked_sys}' is strictly forbidden.")

        # 3. Check blocked secret filenames and extensions
        filename = parts[-1].lower()
        if filename in [f.lower() for f in BLOCKED_SECRET_FILES]:
            raise PathSecurityError(f"Security violation: Access to secret file '{filename}' is strictly forbidden.")

        for ext in BLOCKED_SECRET_EXTENSIONS:
            if filename.endswith(ext):
                raise PathSecurityError(f"Security violation: Access to sensitive file type '{ext}' is strictly forbidden.")

        # 4. Resolve normalized path relative to workspace
        # Strip leading slashes to keep inside workspace
        normalized_relative = os.path.normpath(clean_path_str).replace("\\", "/")
        if normalized_relative.startswith("/"):
            normalized_relative = normalized_relative.lstrip("/")
        
        if normalized_relative.startswith("..") or "/../" in normalized_relative:
            raise PathSecurityError(f"Path traversal detected: Path '{raw_path}' escapes workspace boundary.")

        return normalized_relative
