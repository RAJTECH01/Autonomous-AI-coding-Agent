from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.core.exceptions import DomainError
from app.core.exception_handlers import domain_exception_handler, global_exception_handler
from app.api.middlewares.observability import ObservabilityMiddleware
from app.api.v1.router import api_router

# Setup structured logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up", version=settings.VERSION, env=settings.ENVIRONMENT)

    yield

    # --- Graceful shutdown -------------------------------------------------
    # Uvicorn has already stopped accepting connections and finished in-flight
    # requests by the time we get here. Everything below releases resources that
    # would otherwise leak across a restart or rolling deploy.
    logger.info("Application shutting down, releasing resources")

    # 1. Warn about agent runs still executing. FastAPI BackgroundTasks are not
    #    tracked in a cancellable registry, so they cannot be drained here; a
    #    restart terminates them. Surfacing the count makes the data loss
    #    visible in logs instead of silent.
    try:
        from app.services.background_job_monitor import background_job_monitor

        in_flight = background_job_monitor.get_job_summary().get("running", 0)
        if in_flight:
            logger.warning(
                "Terminating with agent runs still in flight; their progress is lost",
                running_jobs=in_flight,
            )
    except Exception as exc:  # never block shutdown on telemetry
        logger.warning("Could not read background job summary during shutdown", error=str(exc))

    # 2. Destroy sandbox containers and their temp workspaces. Without this,
    #    every restart orphans `sb_*` containers and /tmp directories on the
    #    Docker host.
    try:
        from app.api.v1.endpoints.sessions import SANDBOX_ADAPTER

        await SANDBOX_ADAPTER.destroy_all_sandboxes()
        logger.info("Sandbox containers destroyed")
    except Exception as exc:
        logger.error("Failed to destroy sandboxes during shutdown", error=str(exc))

    # 3. Close database connections so PostgreSQL does not hold sockets open
    #    until its own timeout expires.
    try:
        from app.infrastructure.db.session import engine

        await engine.dispose()
        logger.info("Database connection pool disposed")
    except Exception as exc:
        logger.error("Failed to dispose database engine during shutdown", error=str(exc))

    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    lifespan=lifespan,
)

# Production Observability Middleware
app.add_middleware(ObservabilityMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralized Exception Handlers
#
# The type: ignore is a known Starlette typing limitation, not a defect here.
# add_exception_handler is annotated to accept a handler taking `Exception`, but
# Starlette dispatches by the registered class, so a handler narrowed to
# DomainError is correct at runtime. Typing it as Starlette demands would force
# an isinstance check that can never fail.
app.add_exception_handler(DomainError, domain_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, global_exception_handler)

# Register v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
