"""Database Engine & Session Factory for Promptee.

Supports both PostgreSQL (preferred) and SQLite (fallback) via environment variables.
Provides async SQLAlchemy engine and session management.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
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
    """Create all database tables.

    Safe to call multiple times -- SQLAlchemy ``create_all`` is idempotent
    for existing tables. For SQLite, also ensures data directory exists.
    """
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

    if "postgresql" in DATABASE_URL:
        logger.info("Database tables created / verified in PostgreSQL")
    else:
        logger.info("Database tables created / verified in SQLite")
