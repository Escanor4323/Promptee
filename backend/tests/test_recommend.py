"""Tests for POST /api/v1/recommend.

Verifies that full parent text is returned from SQLite (not Milvus fragments),
that empty Milvus results produce an empty response, that empty queries are
rejected, and that reranker failures fall back gracefully.
"""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import app.db.sqlite as sqlite_module
from app.db.sqlite import Base
from app.main import create_app
from app.models.templates import Template

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)

_DUMMY_VECTOR = np.zeros(384, dtype=np.float32)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def rec_client():
    """AsyncClient backed by in-memory SQLite."""
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


async def _seed_template(full_text: str, title: str = "Test Prompt") -> int:
    """Insert a Template row and return its id."""
    content_hash = hashlib.sha256(full_text.encode()).hexdigest()
    async with TestSessionLocal() as session:
        tmpl = Template(
            milvus_id=None,
            title=title,
            objective="Test objective",
            variables=json.dumps(["ROLE"]),
            full_text=full_text,
            content_hash=content_hash,
        )
        session.add(tmpl)
        await session.flush()
        tmpl_id = tmpl.id
        await session.commit()
    return tmpl_id


def _milvus_hit(template_id: int, score: float = 0.9) -> dict:
    return {
        "id": 42,
        "template_id": template_id,
        "title": "Test Prompt",
        "objective": "Test objective",
        "full_text": "fragment only",
        "variables": ["ROLE"],
        "score": score,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recommend_returns_full_parent_text(rec_client: AsyncClient):
    """full_text in the response must come from SQLite, not the Milvus fragment."""
    full_text = "Full prompt text here [ROLE]"
    tmpl_id = await _seed_template(full_text)

    with (
        patch("app.routers.recommend.embed", return_value=_DUMMY_VECTOR),
        patch("app.routers.recommend.bm25_query_vector", return_value={}),
        patch(
            "app.routers.recommend.milvus_search",
            return_value=[_milvus_hit(tmpl_id)],
        ),
        patch(
            "app.routers.recommend.rerank",
            new_callable=AsyncMock,
            return_value=[{**_milvus_hit(tmpl_id), "hybrid_score": 0.9}],
        ),
    ):
        resp = await rec_client.post(
            "/api/v1/recommend",
            json={"query": "help me write code", "top_k": 5},
        )

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["full_text"] == full_text


@pytest.mark.asyncio
async def test_recommend_empty_milvus_returns_empty_list(rec_client: AsyncClient):
    """When Milvus returns no hits the response is {'results': []}."""
    with (
        patch("app.routers.recommend.embed", return_value=_DUMMY_VECTOR),
        patch("app.routers.recommend.bm25_query_vector", return_value={}),
        patch("app.routers.recommend.milvus_search", return_value=[]),
    ):
        resp = await rec_client.post(
            "/api/v1/recommend",
            json={"query": "anything", "top_k": 5},
        )

    assert resp.status_code == 200
    assert resp.json() == {"results": []}


@pytest.mark.asyncio
async def test_recommend_empty_query_returns_400(rec_client: AsyncClient):
    """A whitespace-only query must be rejected with HTTP 400.

    An empty string ("") is caught earlier by Pydantic's min_length=1 (→ 422).
    A whitespace-only string ("   ") passes Pydantic but fails the router's
    `request.query.strip()` guard which raises HTTPException(400).
    """
    with patch("app.routers.recommend.embed", return_value=_DUMMY_VECTOR):
        resp = await rec_client.post(
            "/api/v1/recommend",
            json={"query": "   ", "top_k": 5},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_recommend_reranker_failure_falls_back_gracefully(rec_client: AsyncClient):
    """If rerank raises, the router falls back to semantic order and still returns 200."""
    full_text = "Fallback prompt [ROLE]"
    tmpl_id = await _seed_template(full_text, title="Fallback Prompt")
    hit = _milvus_hit(tmpl_id)

    with (
        patch("app.routers.recommend.embed", return_value=_DUMMY_VECTOR),
        patch("app.routers.recommend.bm25_query_vector", return_value={}),
        patch("app.routers.recommend.milvus_search", return_value=[hit]),
        patch(
            "app.routers.recommend.rerank",
            new_callable=AsyncMock,
            side_effect=RuntimeError("reranker exploded"),
        ),
    ):
        resp = await rec_client.post(
            "/api/v1/recommend",
            json={"query": "find me a prompt", "top_k": 5},
        )

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_recommend_template_id_zero_returns_empty_full_text(rec_client: AsyncClient):
    """template_id=0 is the sentinel for 'no template'; full_text must be empty string."""
    sentinel_hit = {
        "id": 99,
        "template_id": 0,
        "title": "Orphan",
        "objective": "",
        "full_text": "some fragment",
        "variables": [],
        "score": 0.5,
    }

    with (
        patch("app.routers.recommend.embed", return_value=_DUMMY_VECTOR),
        patch("app.routers.recommend.bm25_query_vector", return_value={}),
        patch("app.routers.recommend.milvus_search", return_value=[sentinel_hit]),
        patch(
            "app.routers.recommend.rerank",
            new_callable=AsyncMock,
            return_value=[{**sentinel_hit, "hybrid_score": 0.5}],
        ),
    ):
        resp = await rec_client.post(
            "/api/v1/recommend",
            json={"query": "any query", "top_k": 5},
        )

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["full_text"] == ""
    assert results[0]["template_id"] == 0
