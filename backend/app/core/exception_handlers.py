from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.core.exceptions import (
    AccountLockedError,
    DomainError,
    PersistenceError,
    PlanIntegrityError,
    RunClaimError,
    ResourceNotFoundError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ToolExecutionError,
    SandboxExecutionError,
)
from app.core.rate_limiter import RateLimitExceededError
from app.core.logging import logger


def get_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    correlation_id = get_correlation_id(request)
    headers: dict = {}

    if isinstance(exc, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = "RESOURCE_NOT_FOUND"
    elif isinstance(exc, RateLimitExceededError):
        # Throttling needs its own status and a backoff hint, otherwise clients
        # cannot behave correctly and proxies cannot shed load (finding DOS-06).
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
        code = "RATE_LIMIT_EXCEEDED"
        headers["Retry-After"] = str(getattr(exc, "retry_after_seconds", 60))
    elif isinstance(exc, AccountLockedError):
        status_code = status.HTTP_423_LOCKED
        code = "ACCOUNT_LOCKED"
        headers["Retry-After"] = str(getattr(exc, "retry_after_seconds", 900))
    elif isinstance(exc, AuthenticationError):
        status_code = status.HTTP_401_UNAUTHORIZED
        code = "AUTHENTICATION_FAILED"
    elif isinstance(exc, AuthorizationError):
        status_code = status.HTTP_403_FORBIDDEN
        code = "ACCESS_DENIED"
    elif isinstance(exc, PlanIntegrityError):
        # 409: the approved plan no longer matches what is stored. The caller has to
        # re-plan and re-approve; retrying the same request cannot succeed.
        status_code = status.HTTP_409_CONFLICT
        code = "PLAN_INTEGRITY_VIOLATION"
    elif isinstance(exc, RunClaimError):
        # 409: another worker or request already owns this transition.
        status_code = status.HTTP_409_CONFLICT
        code = "RUN_ALREADY_CLAIMED"
    elif isinstance(exc, PersistenceError):
        # 500 deliberately: durable storage failed, which is our fault, not the
        # caller's. The message is generic; the correlation id is the link to the log.
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        code = "PERSISTENCE_FAILURE"
    elif isinstance(exc, (ToolExecutionError, SandboxExecutionError)):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        code = "EXECUTION_ERROR"
    else:
        status_code = status.HTTP_400_BAD_REQUEST
        code = "DOMAIN_ERROR"

    logger.warning("Domain exception caught", code=code, detail=str(exc), correlation_id=correlation_id)

    # A PersistenceError's message can carry driver detail - connection strings, table
    # and column names - because it wraps a database exception. The full text is
    # logged above with the correlation id; the client gets a generic message. Every
    # other DomainError is authored by this codebase and is safe to return verbatim.
    client_message = (
        "A storage failure prevented this operation from completing. "
        "The run was not started or has been marked failed; no partial state was kept."
        if isinstance(exc, PersistenceError)
        else str(exc)
    )

    return JSONResponse(
        status_code=status_code,
        headers=headers or None,
        content={
            "error": {
                "code": code,
                "message": client_message,
                "correlation_id": correlation_id
            }
        }
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = get_correlation_id(request)
    logger.error("Unhandled server exception", error=str(exc), correlation_id=correlation_id, exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal server error occurred.",
                "correlation_id": correlation_id
            }
        }
    )
