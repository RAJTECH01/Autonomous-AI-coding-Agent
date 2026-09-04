import logging
import sys
import contextvars
from typing import Optional, Dict, Any
import structlog
from app.core.config import settings

# Context Variables for Distributed Observability Tracing
correlation_id_var = contextvars.ContextVar("correlation_id", default="")
request_id_var = contextvars.ContextVar("request_id", default="")
run_id_var = contextvars.ContextVar("run_id", default="")
tool_call_id_var = contextvars.ContextVar("tool_call_id", default="")


def set_correlation_id(val: str) -> None:
    correlation_id_var.set(val)

def set_request_id(val: str) -> None:
    request_id_var.set(val)

def set_run_id(val: str) -> None:
    run_id_var.set(val)

def set_tool_call_id(val: str) -> None:
    tool_call_id_var.set(val)

def get_correlation_id() -> str:
    return correlation_id_var.get()

def get_request_id() -> str:
    return request_id_var.get()

def get_run_id() -> str:
    return run_id_var.get()

def get_tool_call_id() -> str:
    return tool_call_id_var.get()


SENSITIVE_KEYS = {
    "password", "password_hash", "new_password", "old_password",
    "token", "access_token", "refresh_token", "reset_token", "verification_token", "jwt", "bearer",
    "secret", "secret_key", "api_key", "apikey", "authorization", "cookie", "x-api-key",
    "env", "environment_variables", "private_key", "credentials"
}


def redact_sensitive_data(logger, method_name, event_dict):
    def redact_val(k, v):
        if any(sens in str(k).lower() for sens in SENSITIVE_KEYS):
            return "[REDACTED]"
        if isinstance(v, dict):
            return {sub_k: redact_val(sub_k, sub_v) for sub_k, sub_v in v.items()}
        if isinstance(v, list):
            return [redact_val(k, item) if isinstance(item, dict) else item for item in v]
        return v

    return {k: redact_val(k, v) for k, v in event_dict.items()}


def add_observability_context(logger, method_name, event_dict):
    """Inject active correlation_id, request_id, run_id, tool_call_id into every log event."""
    cid = get_correlation_id()
    req_id = get_request_id()
    run_id = get_run_id()
    t_id = get_tool_call_id()

    if cid:
        event_dict["correlation_id"] = cid
    if req_id:
        event_dict["request_id"] = req_id
    if run_id:
        event_dict["run_id"] = run_id
    if t_id:
        event_dict["tool_call_id"] = t_id

    return event_dict


def setup_logging():
    logging_level = logging.DEBUG if settings.DEBUG else logging.INFO

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        add_observability_context,
        structlog.processors.add_log_level,
        redact_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if settings.ENVIRONMENT == "development" and settings.DEBUG:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    else:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer()
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging_level),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging_level,
    )


logger = structlog.get_logger()
