import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        
        # Bind correlation_id to structlog context for request lifetime
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        
        # Store in request state for downstream handlers
        request.state.correlation_id = correlation_id
        
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
