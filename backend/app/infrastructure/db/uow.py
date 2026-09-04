"""Worker-scoped database session management.

Deliberately separate from ``get_db`` in session.py. That dependency is
request-scoped: FastAPI commits and closes it when the request ends, which for
versions >= 0.106 happens *before* background tasks run. A long-running agent run
that borrowed a request session would therefore be writing through a closed
connection.

This module gives any non-request caller - Celery tasks, beat jobs, scripts - its own
session with the same commit/rollback discipline.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PersistenceError
from app.core.logging import logger
from app.infrastructure.db.session import AsyncSessionLocal


@asynccontextmanager
async def unit_of_work() -> AsyncGenerator[AsyncSession, None]:
    """Open a session, commit on success, roll back on failure, always close.

    Usage::

        async with unit_of_work() as session:
            repo = AgentRepository(session)
            ...
        # committed here, or rolled back if the body raised

    The session is closed by the ``async with AsyncSessionLocal()`` block even when
    commit or rollback itself fails, so a worker cannot leak a connection back into
    the pool in an unknown state.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            # Roll back before re-raising so the connection returns to the pool clean.
            # A failure inside rollback is logged and swallowed because the original
            # exception is the one worth propagating.
            try:
                await session.rollback()
            except Exception as rollback_error:
                logger.error(
                    "Rollback failed while unwinding a unit of work",
                    error=str(rollback_error),
                )
            raise


@asynccontextmanager
async def transactional_unit_of_work() -> AsyncGenerator[AsyncSession, None]:
    """Like :func:`unit_of_work`, but translates storage failures into PersistenceError.

    Used where the caller's contract is "this either persisted or the operation
    fails" - creating a run, recording an approval, transitioning state. Wrapping the
    driver exception keeps SQLAlchemy types out of the domain layer while preserving
    the original as ``__cause__`` for the logs.
    """
    try:
        async with unit_of_work() as session:
            yield session
    except PersistenceError:
        raise
    except Exception as exc:
        raise PersistenceError(f"Durable write failed: {exc}") from exc
