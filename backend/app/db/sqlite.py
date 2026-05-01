"""SQLite Engine & Session Factory for Promptee.

Provides async SQLAlchemy engine bound to a configurable SQLite path,
an async session context manager, and a table-creation utility.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)

# Configurable SQLite database path (default: ./data/promptee.db)
DATABASE_DIR: str = os.getenv("PROMPTEE_DB_DIR", "./data")
DATABASE_PATH: str = os.getenv(
    "PROMPTEE_DB_PATH",
    os.path.join(DATABASE_DIR, "promptee.db"),
)
DATABASE_URL: str = f"sqlite+aiosqlite:///{DATABASE_PATH}"


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
    """Create the data directory and all database tables.

    Safe to call multiple times -- SQLAlchemy ``create_all`` is idempotent
    for existing tables.
    """
    db_dir: str = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        logger.info("Ensured database directory exists: %s", db_dir)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created / verified at %s", DATABASE_PATH)
