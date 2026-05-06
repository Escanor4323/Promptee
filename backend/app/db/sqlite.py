"""Database Engine & Session Factory for Promptee.

Supports both PostgreSQL (preferred) and SQLite (fallback) via environment variables.
Provides async SQLAlchemy engine and session management.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)


def _construct_database_url() -> str:
    """Construct DATABASE_URL from environment variables.

    Priority:
    1. DATABASE_URL if explicitly set
    2. PostgreSQL if PG_* env vars present
    3. SQLite as fallback (backwards compatible)
    """
    # Explicit DATABASE_URL takes precedence
    if explicit_url := os.getenv("DATABASE_URL"):
        logger.info("Using explicit DATABASE_URL")
        return explicit_url

    # PostgreSQL configuration
    pg_host = os.getenv("PG_HOST")
    pg_port = os.getenv("PG_PORT", "5432")
    pg_user = os.getenv("PG_USER", "promptee")
    pg_password = os.getenv("PG_PASSWORD", "promptee_password")
    pg_database = os.getenv("PG_DATABASE", "promptee")

    if pg_host:
        url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        logger.info("Using PostgreSQL database at %s:%s/%s", pg_host, pg_port, pg_database)
        return url

    # SQLite fallback (backwards compatible)
    db_dir = os.getenv("PROMPTEE_DB_DIR", "./data")
    db_path = os.getenv(
        "PROMPTEE_DB_PATH",
        os.path.join(db_dir, "promptee.db"),
    )
    logger.info("Using SQLite database at %s", db_path)
    return f"sqlite+aiosqlite:///{db_path}"


DATABASE_URL: str = _construct_database_url()


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all Promptee models."""

    pass


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session.

    Usage::

        async with async_session() as session:
            result = await session.execute(select(Template))
    """
    session: AsyncSession = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Create all database tables and verify they exist.

    Safe to call multiple times -- SQLAlchemy ``create_all`` is idempotent
    for existing tables. For SQLite, also ensures data directory exists.

    Raises:
        RuntimeError: If database tables cannot be created or verified.
    """
    try:
        # Ensure SQLite data directory exists (no-op for PostgreSQL)
        if "sqlite" in DATABASE_URL:
            db_dir = os.path.dirname(
                os.getenv("PROMPTEE_DB_PATH", os.path.join("./data", "promptee.db"))
            )
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
                logger.info("Ensured database directory exists: %s", db_dir)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.debug("Base.metadata.create_all() completed")

        # Verify all required tables were created
        await verify_tables_exist(engine)
        status = await get_database_status(engine)
        logger.info(
            "Database initialized: %d tables at %s (size: %s bytes)",
            status["table_count"],
            status["db_path"],
            status["db_size"],
        )
    except Exception as exc:
        logger.error(
            "Failed to initialize database: %s",
            exc,
            exc_info=True,
        )
        raise RuntimeError(f"Database initialization failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

# All tables that must exist for the application to function correctly.
REQUIRED_TABLES: frozenset[str] = frozenset(
    {"jobs", "templates", "addon_templates", "executions", "feedback", "models", "model_preferences"}
)


async def verify_tables_exist(db_engine: AsyncEngine | None = None) -> bool:
    """Verify all required application tables are present in the database.

    Args:
        db_engine: Optional SQLAlchemy async engine to use.  Defaults to the
            module-level ``engine``.

    Returns:
        True when all required tables are present.

    Raises:
        RuntimeError: When one or more required tables are missing, listing
            each missing table name in the message.
    """
    from sqlalchemy import inspect as sa_inspect

    target_engine = db_engine if db_engine is not None else engine

    async with target_engine.connect() as conn:
        existing: set[str] = set(
            await conn.run_sync(
                lambda sync_conn: sa_inspect(sync_conn).get_table_names()
            )
        )

    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        raise RuntimeError(
            f"Required database tables are missing: {', '.join(missing)}"
        )
    return True


async def get_database_status(db_engine: AsyncEngine | None = None) -> dict:
    """Return a snapshot of database health metadata.

    Args:
        db_engine: Optional SQLAlchemy async engine to use.  Defaults to the
            module-level ``engine``.

    Returns:
        A dict with keys:

        - ``db_path`` (str): The database connection URL / path.
        - ``db_size`` (int): File size in bytes for SQLite; ``-1`` for other
          backends or when size is unavailable.
        - ``table_count`` (int): Number of tables currently in the database.
    """
    import pathlib
    from sqlalchemy import inspect as sa_inspect

    target_engine = db_engine if db_engine is not None else engine

    async with target_engine.connect() as conn:
        table_names: list[str] = await conn.run_sync(
            lambda sync_conn: sa_inspect(sync_conn).get_table_names()
        )

    url_str = str(target_engine.url)
    db_size: int = -1
    if "sqlite" in url_str:
        # Extract file path from e.g. sqlite+aiosqlite:///./data/promptee.db
        raw_path = url_str.split("///", 1)[-1]
        if raw_path and raw_path != ":memory:":
            p = pathlib.Path(raw_path)
            db_size = p.stat().st_size if p.exists() else 0

    return {
        "db_path": url_str,
        "db_size": db_size,
        "table_count": len(table_names),
    }
