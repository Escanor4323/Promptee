"""Test models API endpoints."""

import pytest
from httpx import AsyncClient

from backend.app.models.models import Model


@pytest.mark.asyncio
async def test_list_models_empty(async_client: AsyncClient) -> None:
    """Test listing models returns empty list initially."""
    response = await async_client.get("/api/v1/models")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_register_model(async_client: AsyncClient) -> None:
    """Test registering a new model."""
    response = await async_client.post("/api/v1/models", json={
        "name": "claude-opus-4-7",
        "type": "claude",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "claude-opus-4-7"
    assert data["type"] == "claude"
    assert data["id"] is not None
    assert data["created_at"] is not None


@pytest.mark.asyncio
async def test_register_duplicate_model(async_client: AsyncClient) -> None:
    """Test registering duplicate model returns 409 conflict."""
    # Register first model
    await async_client.post("/api/v1/models", json={
        "name": "claude-opus-4-7",
        "type": "claude",
    })

    # Try to register same model again
    response = await async_client.post("/api/v1/models", json={
        "name": "claude-opus-4-7",
        "type": "claude",
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_models_after_register(async_client: AsyncClient) -> None:
    """Test listing models after registering one."""
    # Register a model
    await async_client.post("/api/v1/models", json={
        "name": "claude-sonnet-4-6",
        "type": "claude",
    })

    # List models
    response = await async_client.get("/api/v1/models")
    assert response.status_code == 200
    models = response.json()
    assert len(models) == 1
    assert models[0]["name"] == "claude-sonnet-4-6"
