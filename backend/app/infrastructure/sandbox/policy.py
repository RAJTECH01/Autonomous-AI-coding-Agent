import os
import re
from typing import Dict, Any, Optional, Set, Tuple


class SecurityPolicyError(Exception):
    """Raised when a security policy rule is violated."""
    pass


class SandboxSecurityPolicy:
    """
    Enforces security isolation rules, environment variable sanitization,
    output size limits, and path boundaries for sandbox execution.
    """

    # Approved environment variables allowed to pass into container
    ALLOWED_ENV_VARS: Set[str] = {
        "PATH",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "HOME",
        "TERM",
        "TZ",
    }

    # Forbidden environment variable names or key patterns (case-insensitive)
    SENSITIVE_KEY_PATTERNS = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"SECRET",
            r"KEY",
            r"TOKEN",
            r"PASSWORD",
            r"PASS",
            r"AUTH",
            r"CREDENTIAL",
            r"AWS_",
            r"DATABASE_",
            r"POSTGRES_",
            r"REDIS_",
            r"OPENAI_",
            r"ANTHROPIC_",
            r"GEMINI_",
        ]
    ]

    @classmethod
    def sanitize_environment(
        cls,
        user_env: Optional[Dict[str, str]] = None,
        allow_custom: bool = True
    ) -> Dict[str, str]:
        """
        Sanitizes environment variables to prevent leaking host credentials
        or sensitive configuration into sandbox containers.
        """
        if os.name == "nt":
            sanitized: Dict[str, str] = {
                "PATH": os.environ.get("PATH", ""),
                "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows"),
                "ComSpec": os.environ.get("ComSpec", "C:\\Windows\\System32\\cmd.exe"),
                "PYTHONUNBUFFERED": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "TMPDIR": os.environ.get("TEMP", "C:\\Windows\\Temp"),
                "HOME": os.environ.get("USERPROFILE", "C:\\Users"),
            }
        else:
            sanitized: Dict[str, str] = {
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "PYTHONUNBUFFERED": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                # nosec B108 - not a temp file created on this host. This is the
                # TMPDIR value handed to the sandbox container, where /tmp is a
                # noexec,nosuid tmpfs mounted by get_container_security_options.
                "TMPDIR": "/tmp",
                "HOME": "/workspace",
            }


        if user_env and allow_custom:
            for key, val in user_env.items():
                key_upper = key.upper()
                # Check for sensitive key patterns
                if any(pat.search(key_upper) for pat in cls.SENSITIVE_KEY_PATTERNS):
                    continue  # Drop sensitive environment variable
                sanitized[key] = str(val)

        return sanitized

    @classmethod
    def truncate_output(cls, content: str, max_bytes: int = 1048576) -> Tuple[str, bool]:
        """
        Truncates execution output if it exceeds max_bytes to prevent memory exhaustion DoS.
        Returns (truncated_content, was_truncated).
        """
        if not content:
            return "", False

        content_bytes = content.encode("utf-8", errors="replace")
        if len(content_bytes) <= max_bytes:
            return content, False

        truncated_bytes = content_bytes[:max_bytes]
        notice = f"\n\n[TRUNCATED: Maximum execution output limit of {max_bytes} bytes exceeded]".encode("utf-8")
        final_str = truncated_bytes.decode("utf-8", errors="ignore") + notice.decode("utf-8")
        return final_str, True

    @classmethod
    def validate_workspace_relative_path(cls, workdir: str, file_path: str) -> str:
        """
        Ensures target path resolves strictly inside the designated workspace boundary,
        preventing directory traversal attacks (`../`).
        """
        normalized_workdir = os.path.abspath(workdir)
        target_path = os.path.abspath(os.path.join(normalized_workdir, file_path))

        if not target_path.startswith(normalized_workdir):
            raise SecurityPolicyError(
                f"Access denied: Target path '{file_path}' escapes workspace boundary '{workdir}'"
            )
        return target_path

    @classmethod
    def get_container_security_options(
        cls,
        max_cpus: float = 2.0,
        max_memory_mb: int = 512,
        max_pids: int = 100,
        log_max_size: str = "5m",
        network_enabled: bool = False,
    ) -> Dict[str, Any]:
        """
        Returns Docker container run kwargs enforcing security isolation requirements.
        """
        options: Dict[str, Any] = {
            "read_only": True,  # Requirement 8: Read-only root filesystem
            "cap_drop": ["ALL"],  # Requirement 13: Drop all capabilities
            "security_opt": ["no-new-privileges:true"],  # Requirement 13: Prevent privilege escalation
            "privileged": False,  # Requirement 13: No privileged container
            "network_mode": "bridge" if network_enabled else "none",  # Requirement 7: Network disabled by default
            "nano_cpus": int(max_cpus * 1e9),  # Requirement 2: CPU limits
            "mem_limit": f"{max_memory_mb}m",  # Requirement 3: Memory limits
            "memswap_limit": f"{max_memory_mb}m",  # Disallow swap abuse
            "pids_limit": max_pids,  # Requirement 4: Process limits
            "tmpfs": {
                # nosec B108 - a tmpfs mount target inside the sandbox container,
                # deliberately noexec and nosuid and size-capped, not a
                # predictable temp path on the host.
                "/tmp": "rw,noexec,nosuid,size=64m",
                "/run": "rw,noexec,nosuid,size=16m",
            },
            "log_config": {
                "type": "json-file",
                "config": {"max-size": log_max_size, "max-file": "2"},
            },
        }
        return options
