import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import (
    set_correlation_id,
    set_request_id,
    logger,
    redact_sensitive_data,
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Production Observability Middleware:
    1. Injects and correlates X-Correlation-ID and X-Request-ID.
    2. Binds IDs to structlog contextvars for downstream logging.
    3. Measures request latency and logs structured JSON summaries with sensitive header redaction.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        set_correlation_id(correlation_id)
        set_request_id(request_id)

        request.state.correlation_id = correlation_id
        request.state.request_id = request_id

        start_time = time.time()

        try:
            response: Response = await call_next(request)
            duration_ms = round((time.time() - start_time) * 1000, 2)

            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Request-ID"] = request_id

            # Log clean request summary
            logger.info(
                "HTTP Request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                request_id=request_id,
            )
            return response
        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "HTTP Request Exception",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
                correlation_id=correlation_id,
                request_id=request_id,
                exc_info=True,
            )
            raise exc
