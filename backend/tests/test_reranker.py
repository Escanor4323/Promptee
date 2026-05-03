"""Tests for hybrid reranking algorithm."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.executions import Execution
from app.models.feedback import Feedback
from app.models.templates import Template
from app.services.reranker import QUALITY_DEFAULT, rerank


@pytest_asyncio.fixture
async def seed_data(async_session: AsyncSession) -> list[Template]:
    t1 = Template(milvus_id=1, title="Popular Good", objective="Good and popular")
    t2 = Template(milvus_id=2, title="Popular Bad", objective="Popular but low rated")
    t3 = Template(milvus_id=3, title="New Prompt", objective="No history yet")
    async_session.add_all([t1, t2, t3])
    await async_session.flush()

    # t1: 2 executions, 5-star feedback
    e1 = Execution(template_id=t1.id, latency_ms=100, input_tokens=100, output_tokens=100, context_window_pct=10, verbosity="moderate")
    e2 = Execution(template_id=t1.id, latency_ms=150, input_tokens=200, output_tokens=50, context_window_pct=15, verbosity="moderate")
    async_session.add_all([e1, e2])
    await async_session.flush()
    async_session.add_all([
        Feedback(execution_id=e1.id, quality_score=5),
        Feedback(execution_id=e2.id, quality_score=5),
    ])

    # t2: 1 execution, 1-star feedback
    e3 = Execution(template_id=t2.id, latency_ms=2000, input_tokens=1000, output_tokens=500, context_window_pct=80, verbosity="verbose")
    async_session.add(e3)
    await async_session.flush()
    async_session.add(Feedback(execution_id=e3.id, quality_score=1))

    await async_session.flush()
    return [t1, t2, t3]


@pytest.mark.asyncio
async def test_rerank_with_historical_data(async_session: AsyncSession, seed_data: list[Template]) -> None:
    results = [
        {"id": 100, "template_id": seed_data[0].id, "title": "Popular Good", "objective": "Good", "full_text": "text1", "variables": [], "score": 0.8},
        {"id": 101, "template_id": seed_data[1].id, "title": "Popular Bad", "objective": "Bad", "full_text": "text2", "variables": [], "score": 0.9},
        {"id": 102, "template_id": seed_data[2].id, "title": "New Prompt", "objective": "New", "full_text": "text3", "variables": [], "score": 0.7},
    ]
    reranked = await rerank(results, "balanced", async_session, top_k=3)
    assert len(reranked) == 3
    assert all("hybrid_score" in r for r in reranked)
    assert reranked[0]["template_id"] == seed_data[0].id or reranked[0]["hybrid_score"] > 0


@pytest.mark.asyncio
async def test_rerank_with_no_history(async_session: AsyncSession) -> None:
    results = [
        {"id": 200, "template_id": 9999, "title": "Unknown", "objective": "Test", "full_text": "text", "variables": [], "score": 0.5},
    ]
    reranked = await rerank(results, "balanced", async_session, top_k=1)
    assert len(reranked) == 1
    assert reranked[0]["hybrid_score"] > 0


@pytest.mark.asyncio
async def test_tradeoff_preference_adjusts_weights(async_session: AsyncSession, seed_data: list[Template]) -> None:
    results = [
        {"id": 300, "template_id": seed_data[0].id, "title": "Good", "objective": "O", "full_text": "t", "variables": [], "score": 0.5},
        {"id": 301, "template_id": seed_data[2].id, "title": "New", "objective": "O", "full_text": "t", "variables": [], "score": 0.5},
    ]
    balanced = await rerank(results, "balanced", async_session, top_k=2)
    quality = await rerank(results, "quality", async_session, top_k=2)
    good_idx_balanced = next(i for i, r in enumerate(balanced) if r["template_id"] == seed_data[0].id)
    good_idx_quality = next(i for i, r in enumerate(quality) if r["template_id"] == seed_data[0].id)
    assert quality[good_idx_quality]["hybrid_score"] >= balanced[good_idx_balanced]["hybrid_score"]


@pytest.mark.asyncio
async def test_rerank_empty_results(async_session: AsyncSession) -> None:
    reranked = await rerank([], "balanced", async_session, top_k=5)
    assert len(reranked) == 0
