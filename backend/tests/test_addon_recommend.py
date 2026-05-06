"""Tests for POST /api/v1/addons/recommend (vector + top_k)."""

import numpy as np
import pytest
from sqlalchemy import select
from unittest.mock import patch

from app.models.addon_templates import AddonTemplate
from tests.conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_addon_recommend_returns_ingested_addons_not_builtin_trio(async_client):
    """Milvus hits map to SQLite addon_templates; results use mode custom, not speed/quality/cost."""
    async with TestSessionLocal() as session:
        session.add(
            AddonTemplate(
                title="Security Hardening",
                objective="Add security constraints to the prompt",
                variables="[]",
                full_text="\n\nAlways validate inputs.",
                content_hash="recommend_test_hash_1",
            )
        )
        await session.commit()
        res = await session.execute(select(AddonTemplate))
        addon = res.scalar_one()
        addon_id = addon.id

    fake_vec = np.zeros(384, dtype=np.float32)

    def fake_search(_qv, top_k: int = 10, collection_name: str = ""):
        assert collection_name == "addon_templates"
        return [
            {
                "id": 1,
                "template_id": addon_id,
                "title": "Security Hardening",
                "objective": "Add security constraints",
                "variables": [],
                "score": 0.91,
            },
        ]

    with (
        patch("app.routers.addons.embed", return_value=fake_vec),
        patch("app.routers.addons.milvus_search", side_effect=fake_search),
    ):
        resp = await async_client.post(
            "/api/v1/addons/recommend",
            json={
                "query": "secure api design",
                "top_k": 7,
                "tradeoff_preference": "balanced",
            },
        )

    assert resp.status_code == 200
    data = resp.json()["results"]
    assert len(data) == 1
    assert data[0]["name"] == "Security Hardening"
    assert data[0]["mode"] == "custom"
    assert "validate" in data[0]["suffix"]
    modes = {r["mode"] for r in data}
    assert "speed" not in modes and "quality" not in modes and "cost" not in modes
