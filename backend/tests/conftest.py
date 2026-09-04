import pytest
import pytest_asyncio
from typing import AsyncGenerator
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
import app.infrastructure.db.models as db_models
Base = db_models.Base
from app.main import app
from app.infrastructure.db.session import get_db
from app.services.brute_force_service import brute_force_service
from app.core.rate_limiter import rate_limiter

# A file-backed SQLite database rather than ":memory:".
#
# With an in-memory database the schema lives inside a single connection, so the
# suite becomes order-dependent: any test that invalidates that connection (for
# example by opening `engine.begin()` while a session already holds the one
# StaticPool connection, as tests/test_agent_state_machine.py does) silently
# hands the next test an empty database and a cascade of
# "no such table: users" failures. A file-backed database survives connection
# recycling, so tests can run in any order and in any event loop.
import atexit as _atexit
import shutil as _shutil_bootstrap
import tempfile as _tempfile_bootstrap
from pathlib import Path as _Path

_TEST_DB_DIR = _tempfile_bootstrap.mkdtemp(prefix="agent_test_db_")
_atexit.register(_shutil_bootstrap.rmtree, _TEST_DB_DIR, True)

TEST_DATABASE_URL = f"sqlite+aiosqlite:///{(_Path(_TEST_DB_DIR) / 'test.db').as_posix()}"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


# Create the schema once, before any test runs.
#
# WHY THIS IS NEEDED: the autouse fixture below is an *async* fixture, and with
# `asyncio_mode = strict` pytest-asyncio only applies async fixtures to async
# tests. Every sync test (anything taking the TestClient `client` fixture, which
# is most of the auth and API suite) therefore never ran it, and depended on some
# earlier async test having created the tables. That made the suite
# order-dependent: `pytest tests/auth/test_authentication.py::TestAbuseControls`
# failed on its own while passing as part of a full run.
#
# A separate short-lived engine is used and then disposed, rather than
# `test_engine`. test_engine uses StaticPool, so a connection opened here would be
# bound to this now-closed event loop and reused by later tests. Disposing a
# throwaway engine leaves test_engine to open its connection lazily inside the
# test's own loop.
def _bootstrap_schema() -> None:
    import asyncio

    async def _create() -> None:
        bootstrap_engine = create_async_engine(
            TEST_DATABASE_URL, connect_args={"check_same_thread": False}
        )
        try:
            async with bootstrap_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await bootstrap_engine.dispose()

    asyncio.run(_create())


_bootstrap_schema()


@pytest.fixture(autouse=True)
def _reset_abuse_controls():
    """Reset process-global abuse-control state around every test, sync or async.

    BruteForceProtectionService and RateLimiter both keep their counters in plain
    process memory (documented as a known limitation in each). Without a reset
    that applies to sync tests too, failed-login counters from one test leak into
    the next and lockout assertions pass or fail depending on execution order.

    This is a plain sync fixture on purpose: it touches no database and no event
    loop, so pytest applies it uniformly to sync and async tests alike.
    """
    brute_force_service._attempts.clear()
    rate_limiter._records.clear()
    yield
    brute_force_service._attempts.clear()
    rate_limiter._records.clear()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    # Redundant with _reset_abuse_controls for async tests, kept so this fixture
    # remains correct if used on its own.
    brute_force_service._attempts.clear()
    rate_limiter._records.clear()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("PRAGMA foreign_keys = OFF;"))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.execute(text("PRAGMA foreign_keys = ON;"))


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Shared fixtures for the production test strategy (additive: nothing above is
# modified). See tests/support/ for the realistic fakes these build on.
# ---------------------------------------------------------------------------
import shutil as _shutil
import tempfile as _tempfile

from tests.support.factories import make_run, write_workspace
from tests.support.sandboxes import InProcessSandbox, RecordingSandbox


@pytest.fixture
def workspace_dir():
    """A real, empty project directory on disk, removed afterwards."""
    path = _tempfile.mkdtemp(prefix="test_ws_")
    try:
        yield path
    finally:
        _shutil.rmtree(path, ignore_errors=True)


@pytest_asyncio.fixture
async def sandbox():
    """A real-filesystem sandbox honouring the production containment policy."""
    sb = InProcessSandbox()
    sandbox_id = await sb.create_sandbox("test-session")
    try:
        yield sb, sandbox_id
    finally:
        await sb.destroy_sandbox(sandbox_id)


@pytest_asyncio.fixture
async def project_sandbox():
    """Factory: build a sandbox pre-populated with a real project tree."""
    created = []

    async def _build(files: dict):
        source = _tempfile.mkdtemp(prefix="test_src_")
        write_workspace(source, files)
        sb = InProcessSandbox()
        sandbox_id = await sb.create_sandbox("test-session", workspace_path=source)
        created.append((sb, sandbox_id, source))
        return sb, sandbox_id

    try:
        yield _build
    finally:
        for sb, sandbox_id, source in created:
            await sb.destroy_sandbox(sandbox_id)
            _shutil.rmtree(source, ignore_errors=True)


@pytest_asyncio.fixture
async def recording_sandbox():
    """Records command strings without executing them."""
    sb = RecordingSandbox()
    sandbox_id = await sb.create_sandbox("test-session")
    try:
        yield sb, sandbox_id
    finally:
        await sb.destroy_sandbox(sandbox_id)


@pytest.fixture
def agent_run():
    return make_run()


@pytest.fixture
def tool_layer():
    from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer

    return ControlledToolLayer()


@pytest.fixture
def git_binary():
    """Skip the test when git is not installed on the host."""
    path = _shutil.which("git")
    if not path:
        pytest.skip("git binary is not available on this host")
    return path


@pytest.fixture(autouse=True, scope="session")
def _quiet_third_party_logs():
    """The app configures root logging at DEBUG (settings.DEBUG defaults to True),
    which buries assertion output under driver chatter. Keep our own loggers but
    silence the noisy third-party ones."""
    import logging

    for name in ("aiosqlite", "asyncio", "sqlalchemy.engine", "httpx", "httpcore", "docker", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    yield


@pytest_asyncio.fixture
async def db_session():
    """A real AsyncSession against the test engine, rolled back at the end."""
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def db_session_fk():
    """Real session with SQLite foreign-key enforcement switched on."""
    from sqlalchemy import text as _text

    async with TestingSessionLocal() as session:
        await session.execute(_text("PRAGMA foreign_keys = ON;"))
        try:
            yield session
        finally:
            await session.rollback()
