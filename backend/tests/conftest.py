"""Shared pytest fixtures for Promptee backend tests."""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.sqlite import Base
from app.main import create_app

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    import app.db.sqlite as sqlite_module

    original_engine = sqlite_module.engine
    original_session_local = sqlite_module.AsyncSessionLocal

    sqlite_module.engine = test_engine
    sqlite_module.AsyncSessionLocal = TestSessionLocal

    app = create_app()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    sqlite_module.engine = original_engine
    sqlite_module.AsyncSessionLocal = original_session_local


@pytest_asyncio.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session: AsyncSession = TestSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_milvus_results() -> list[dict]:
    return [
        {"id": 1, "template_id": 1, "title": "Code Review", "objective": "Review code for quality", "full_text": "You are a [ROLE] reviewing [LANGUAGE] code", "variables": ["ROLE", "LANGUAGE"], "score": 0.92},
        {"id": 2, "template_id": 2, "title": "Bug Fix Helper", "objective": "Help fix bugs", "full_text": "You are a [ROLE] fixing bugs in [FRAMEWORK]", "variables": ["ROLE", "FRAMEWORK"], "score": 0.85},
        {"id": 3, "template_id": 3, "title": "Test Writer", "objective": "Write unit tests", "full_text": "Write tests for [LANGUAGE] using [FRAMEWORK]", "variables": ["LANGUAGE", "FRAMEWORK"], "score": 0.78},
    ]
