"""End-to-end pipeline tests: ingest -> recommend -> telemetry -> feedback.

Uses real SQLite (in-memory) and mocks Milvus/embedder where needed
to test the full data flow without external service dependencies.
"""

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.sqlite import Base
from app.main import create_app
from app.models.executions import Execution
from app.models.feedback import Feedback
from app.models.templates import Template

import app.db.sqlite as sqlite_module

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture
async def e2e_client() -> AsyncClient:
    """Patched FastAPI client with in-memory SQLite."""
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
async def seeded_templates(e2e_client: AsyncClient) -> list[dict]:
    """Seed templates directly into SQLite for testing."""
    async with sqlite_module.async_session() as session:
        t1 = Template(
            milvus_id=100, title="Code Review",
            objective="Review code for quality",
            variables=json.dumps(["ROLE", "LANGUAGE"]),
        )
        t2 = Template(
            milvus_id=101, title="Bug Fix",
            objective="Fix bugs systematically",
            variables=json.dumps(["ROLE", "FRAMEWORK"]),
        )
        t3 = Template(
            milvus_id=102, title="Test Writer",
            objective="Write comprehensive tests",
            variables=json.dumps(["LANGUAGE", "FRAMEWORK"]),
        )
        session.add_all([t1, t2, t3])
        await session.flush()
        return [
            {
                "id": 100, "template_id": t1.id,
                "title": t1.title, "objective": t1.objective or "",
                "full_text": "Review [LANGUAGE] code as a [ROLE]",
                "variables": ["ROLE", "LANGUAGE"], "score": 0.92,
            },
            {
                "id": 101, "template_id": t2.id,
                "title": t2.title, "objective": t2.objective or "",
                "full_text": "Fix bugs in [FRAMEWORK] as a [ROLE]",
                "variables": ["ROLE", "FRAMEWORK"], "score": 0.85,
            },
            {
                "id": 102, "template_id": t3.id,
                "title": t3.title, "objective": t3.objective or "",
                "full_text": "Write tests for [LANGUAGE] using [FRAMEWORK]",
                "variables": ["LANGUAGE", "FRAMEWORK"], "score": 0.78,
            },
        ]


@pytest.mark.asyncio
async def test_health_check(e2e_client: AsyncClient) -> None:
    response = await e2e_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data


@pytest.mark.asyncio
async def test_submit_telemetry_and_feedback(
    e2e_client: AsyncClient, seeded_templates: list[dict],
) -> None:
    """Full pipeline: submit telemetry then submit feedback."""
    template_id = seeded_templates[0]["template_id"]

    tel_resp = await e2e_client.post("/api/v1/telemetry", json={
        "template_id": template_id,
        "latency_ms": 250.0,
        "input_tokens": 800,
        "output_tokens": 300,
        "context_window_pct": 35.0,
        "verbosity": "moderate",
        "addon_mode": "quality",
    })
    assert tel_resp.status_code == 201
    tel_data = tel_resp.json()
    execution_id = tel_data["id"]
    assert tel_data["template_id"] == template_id
    assert 0.0 < tel_data["tradeoff_speed"] <= 1.0
    assert 0.0 < tel_data["tradeoff_cost"] <= 1.0
    assert 0.0 < tel_data["tradeoff_quality"] <= 1.0

    fb_resp = await e2e_client.post("/api/v1/feedback", json={
        "execution_id": execution_id,
        "quality_score": 5,
        "notes": "Excellent prompt for code review",
    })
    assert fb_resp.status_code == 201
    assert fb_resp.json()["quality_score"] == 5


@pytest.mark.asyncio
async def test_multiple_telemetry_entries(
    e2e_client: AsyncClient, seeded_templates: list[dict],
) -> None:
    """Multiple telemetry submissions build execution history."""
    template_id = seeded_templates[0]["template_id"]

    execution_ids: list[int] = []
    for i in range(3):
        resp = await e2e_client.post("/api/v1/telemetry", json={
            "template_id": template_id,
            "latency_ms": 100.0 + i * 50,
            "input_tokens": 500 + i * 100,
            "output_tokens": 200 + i * 50,
            "context_window_pct": 20.0 + i * 10,
            "verbosity": "moderate",
        })
        assert resp.status_code == 201
        execution_ids.append(resp.json()["id"])

    for eid in execution_ids:
        resp = await e2e_client.post("/api/v1/feedback", json={
            "execution_id": eid,
            "quality_score": 4,
        })
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_telemetry_validates_template_exists(e2e_client: AsyncClient) -> None:
    resp = await e2e_client.post("/api/v1/telemetry", json={
        "template_id": 99999,
        "latency_ms": 100.0,
        "input_tokens": 100,
        "output_tokens": 50,
        "context_window_pct": 10.0,
        "verbosity": "terse",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_feedback_validates_score_range(
    e2e_client: AsyncClient, seeded_templates: list[dict],
) -> None:
    template_id = seeded_templates[0]["template_id"]
    tel_resp = await e2e_client.post("/api/v1/telemetry", json={
        "template_id": template_id,
        "latency_ms": 100.0,
        "input_tokens": 300,
        "output_tokens": 100,
        "context_window_pct": 10.0,
        "verbosity": "terse",
    })
    execution_id = tel_resp.json()["id"]

    for bad_score in [0, 6, -1, 100]:
        resp = await e2e_client.post("/api/v1/feedback", json={
            "execution_id": execution_id,
            "quality_score": bad_score,
        })
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reranking_with_feedback_history(
    seeded_templates: list[dict],
) -> None:
    """Reranker boosts templates with high feedback scores."""
    from app.services.reranker import rerank

    async with sqlite_module.async_session() as session:
        t1_id = seeded_templates[0]["template_id"]
        t2_id = seeded_templates[1]["template_id"]

        e1 = Execution(
            template_id=t1_id, latency_ms=100, input_tokens=100,
            output_tokens=100, context_window_pct=10, verbosity="moderate",
        )
        session.add(e1)
        await session.flush()
        session.add(Feedback(execution_id=e1.id, quality_score=5))

        e2 = Execution(
            template_id=t2_id, latency_ms=2000, input_tokens=2000,
            output_tokens=1000, context_window_pct=80, verbosity="verbose",
        )
        session.add(e2)
        await session.flush()
        session.add(Feedback(execution_id=e2.id, quality_score=1))
        await session.flush()

    async with sqlite_module.async_session() as session:
        results = [
            {
                "id": 100, "template_id": seeded_templates[0]["template_id"],
                "title": "Code Review", "objective": "Review code",
                "full_text": "t1", "variables": [], "score": 0.5,
            },
            {
                "id": 101, "template_id": seeded_templates[1]["template_id"],
                "title": "Bug Fix", "objective": "Fix bugs",
                "full_text": "t2", "variables": [], "score": 0.5,
            },
        ]
        reranked = await rerank(results, "balanced", session, top_k=2)

    assert reranked[0]["template_id"] == seeded_templates[0]["template_id"]
    assert reranked[0]["hybrid_score"] > reranked[1]["hybrid_score"]


@pytest.mark.asyncio
async def test_addon_injection() -> None:
    from app.services.addon import inject_addon, BUILTIN_ADDONS

    base = "You are a code reviewer."
    injected = inject_addon(base, BUILTIN_ADDONS["speed"])
    assert injected.startswith(base)
    assert "raw code" in injected

    quality_injected = inject_addon(base, BUILTIN_ADDONS["quality"])
    assert "step-by-step" in quality_injected


@pytest.mark.asyncio
async def test_chunker_produces_valid_chunks() -> None:
    from app.services.chunker import chunk_file

    chunks = chunk_file("prompts/software-engineering.md")
    assert len(chunks) == 5
    for chunk in chunks:
        assert chunk.title
        assert chunk.objective
        assert len(chunk.variables) > 0

    ds_chunks = chunk_file("prompts/data-science.md")
    assert len(ds_chunks) == 5
