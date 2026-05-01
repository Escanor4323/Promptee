"""Tests for /api/v1/telemetry and /api/v1/feedback endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.executions import Execution
from backend.app.models.feedback import Feedback
from backend.app.models.templates import Template


@pytest_asyncio.fixture
async def seed_template(async_session: AsyncSession) -> Template:
    t = Template(milvus_id=999, title="Test Template", objective="Testing")
    async_session.add(t)
    await async_session.flush()
    return t


@pytest.mark.asyncio
async def test_submit_telemetry(async_client: AsyncClient, seed_template: Template) -> None:
    response = await async_client.post("/api/v1/telemetry", json={
        "template_id": seed_template.id,
        "latency_ms": 150.0,
        "input_tokens": 500,
        "output_tokens": 200,
        "context_window_pct": 25.0,
        "verbosity": "moderate",
        "addon_mode": "speed",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["template_id"] == seed_template.id
    assert data["latency_ms"] == 150.0
    assert 0.0 <= data["tradeoff_speed"] <= 1.0
    assert 0.0 <= data["tradeoff_cost"] <= 1.0


@pytest.mark.asyncio
async def test_submit_feedback(async_client: AsyncClient, seed_template: Template) -> None:
    # First create an execution via telemetry
    tel_resp = await async_client.post("/api/v1/telemetry", json={
        "template_id": seed_template.id,
        "latency_ms": 100.0,
        "input_tokens": 300,
        "output_tokens": 100,
        "context_window_pct": 10.0,
        "verbosity": "terse",
    })
    assert tel_resp.status_code == 201
    execution_id = tel_resp.json()["id"]

    # Then submit feedback
    fb_resp = await async_client.post("/api/v1/feedback", json={
        "execution_id": execution_id,
        "quality_score": 4,
        "notes": "Good prompt",
    })
    assert fb_resp.status_code == 201
    data = fb_resp.json()
    assert data["quality_score"] == 4


@pytest.mark.asyncio
async def test_feedback_validation(async_client: AsyncClient, seed_template: Template) -> None:
    # quality_score out of range
    tel_resp = await async_client.post("/api/v1/telemetry", json={
        "template_id": seed_template.id,
        "latency_ms": 100.0,
        "input_tokens": 300,
        "output_tokens": 100,
        "context_window_pct": 10.0,
        "verbosity": "terse",
    })
    execution_id = tel_resp.json()["id"]

    response = await async_client.post("/api/v1/feedback", json={
        "execution_id": execution_id,
        "quality_score": 0,
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_metrics_computation() -> None:
    from backend.app.services.metrics import compute_speed_score, compute_cost_score
    speed = compute_speed_score(latency_ms=1000.0, input_tokens=500, output_tokens=500)
    assert 0.0 < speed <= 1.0
    cost = compute_cost_score(input_tokens=500, output_tokens=500)
    assert 0.0 < cost <= 1.0
