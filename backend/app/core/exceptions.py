class DomainError(Exception):
    """Base exception for all domain logic failures."""
    pass


class ConfigurationError(DomainError):
    """Raised when application configuration is missing or invalid."""
    pass


class AuthenticationError(DomainError):
    """Raised when authentication credentials fail validation."""
    pass


class AccountLockedError(AuthenticationError):
    """Raised when an account is temporarily locked after repeated failures.

    Distinct from AuthenticationError so the API can answer 423 Locked with a
    Retry-After hint instead of an indistinguishable 401 (finding AUTH-08).
    """

    def __init__(self, message: str, retry_after_seconds: int = 900):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class AuthorizationError(DomainError):
    """Raised when user lacks permissions for a requested operation."""
    pass


class ResourceNotFoundError(DomainError):
    """Raised when a requested resource does not exist."""
    pass


class SandboxExecutionError(DomainError):
    """Raised when a command execution inside the sandbox fails or times out."""
    pass


class ToolExecutionError(DomainError):
    """Raised when a tool input fails validation or runtime execution."""
    pass


class LimitExceededError(DomainError):
    """Raised when agent execution limits (iterations, timeout, tool calls, files) are exceeded."""
    pass


class AgentLoopGuardrailError(DomainError):
    """Raised when an infinite loop or guardrail violation is detected in agent loop."""
    pass


class PersistenceError(DomainError):
    """Raised when durable storage of agent state fails.

    Exists because blocker B3 was invisible: every persistence call site was wrapped
    in ``except Exception: logger.warning(...)``, so a run could execute while nothing
    about it was recorded. Storage failure for a run, a state transition or a plan is
    now a first-class failure that stops execution rather than a log line.
    """
    pass


class PlanIntegrityError(DomainError):
    """Raised when a plan's hash no longer matches the hash a human approved.

    Guards the window between approval and resumption: the plan is re-verified after
    the worker loads it, not only when approval is granted, so a plan mutated in
    between is refused at the point of use.
    """
    pass


class RunClaimError(DomainError):
    """Raised when a worker cannot claim a run because another worker already has it.

    Not an error condition in the usual sense - it is the expected outcome for the
    loser of a race. The conditional UPDATE that transitions run state is the single
    serialization point that makes execution at-most-once.
    """
    pass
