"""Alembic migration environment.

Resolution order for the database URL:
  1. ALEMBIC_DATABASE_URL environment variable (escape hatch for one-off targets,
     e.g. pointing a dry run at a scratch database).
  2. settings.ASYNC_DATABASE_URI, built from the POSTGRES_* environment
     variables that the containers already receive.

The hardcoded sqlalchemy.url in alembic.ini is never used at runtime; it only
keeps `alembic` importable without an environment.

Note the async driver: this file drives an async engine, so the URL must carry an
async dialect (postgresql+asyncpg). Handing it the sync postgresql:// URL raises
"the asyncio extension requires an async driver" because psycopg2 is not a
dependency of this project.
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import settings
from app.infrastructure.db.models import Base

config = context.config


def _database_url() -> str:
    override = os.getenv("ALEMBIC_DATABASE_URL")
    if override:
        return override
    return settings.ASYNC_DATABASE_URI


# Escape any raw '%' so ConfigParser interpolation cannot choke on passwords
# containing percent signs.
config.set_main_option("sqlalchemy.url", _database_url().replace("%", "%%"))

if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render migrations as SQL to stdout without connecting to a database."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
