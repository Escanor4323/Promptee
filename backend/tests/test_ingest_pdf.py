"""Integration tests for the async ingest pipeline.

Uses real in-memory SQLite. Milvus and the sentence-transformer embedder are
mocked so tests run offline without Docker dependencies.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import app.db.sqlite as sqlite_module
from app.db.sqlite import Base
from app.main import create_app
from app.models.templates import Template
from app.services.path_resolver import PathResolution, get_path_resolver

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _passthrough_resolver():
    """FastAPI dependency override: accept any absolute filesystem path."""

    def resolve(path: str) -> PathResolution:
        return PathResolution(
            original=path,
            container_path=Path(path),
            was_translated=False,
            is_relative=False,
        )

    return resolve


def _make_md(path: Path, n_prompts: int) -> None:
    """Write a markdown file with *n_prompts* well-formed prompt sections.

    Uses the `### N. Title` boundary format that chunk_markdown() splits on
    (BOUNDARY_PATTERN = r"(?=^### \\d+\\. )").
    """
    sections = [
        (
            f"### {i + 1}. Prompt {i + 1}\n\n"
            f"**Objective:** Do task {i + 1}.\n\n"
            f"Body text for prompt {i + 1}. Contains [ROLE] variable.\n"
        )
        for i in range(n_prompts)
    ]
    path.write_text("\n".join(sections))


async def _poll_job(client: AsyncClient, job_id: str, timeout: float = 8.0) -> dict:
    """Poll GET /jobs/{job_id} until terminal status or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        resp = await client.get(f"/api/v1/jobs/{job_id}")
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            return data
        if asyncio.get_event_loop().time() > deadline:
            return data
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ingest_client():
    """AsyncClient with in-memory SQLite and passthrough path resolver."""
    original_engine = sqlite_module.engine
    original_session_local = sqlite_module.AsyncSessionLocal

    sqlite_module.engine = test_engine
    sqlite_module.AsyncSessionLocal = TestSessionLocal

    app = create_app()
    app.dependency_overrides[get_path_resolver] = _passthrough_resolver

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    sqlite_module.engine = original_engine
    sqlite_module.AsyncSessionLocal = original_session_local


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_markdown_creates_templates(ingest_client: AsyncClient, tmp_path: Path):
    """Happy path: 2-prompt markdown file -> 2 Template rows in SQLite."""
    md_file = tmp_path / "two_prompts.md"
    _make_md(md_file, n_prompts=2)

    with (
        patch(
            "app.services.ingest_job.embed_batch",
            side_effect=lambda texts: np.zeros((len(texts), 384)),
        ),
        patch("app.services.ingest_job.get_or_create_collection", return_value=MagicMock()),
        patch("app.services.ingest_job.insert_chunks", return_value=None),
    ):
        resp = await ingest_client.post(
            "/api/v1/ingest", json={"paths": [str(md_file)]}
        )
        assert resp.status_code == 202

        job_id = resp.json()["job_id"]
        job_data = await _poll_job(ingest_client, job_id)

    assert job_data["status"] == "completed", f"Job failed: {job_data.get('error')}"

    async with TestSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(Template))
    assert count == 2


@pytest.mark.asyncio
async def test_ingest_empty_file_completes_with_zero_ingested(
    ingest_client: AsyncClient, tmp_path: Path
):
    """A whitespace-only .md file produces no chunks.

    The pipeline's early-exit path marks the job completed with ingested=0
    (validate_parents is only called when at least one chunk exists).
    """
    empty_file = tmp_path / "empty.md"
    empty_file.write_text("   \n\n   \n")

    with (
        patch(
            "app.services.ingest_job.embed_batch",
            side_effect=lambda texts: np.zeros((len(texts), 384)),
        ),
        patch("app.services.ingest_job.get_or_create_collection", return_value=MagicMock()),
        patch("app.services.ingest_job.insert_chunks", return_value=None),
    ):
        resp = await ingest_client.post(
            "/api/v1/ingest", json={"paths": [str(empty_file)]}
        )
        assert resp.status_code == 202

        job_id = resp.json()["job_id"]
        job_data = await _poll_job(ingest_client, job_id)

    assert job_data["status"] == "completed"
    assert job_data["result"]["ingested"] == 0


@pytest.mark.asyncio
async def test_ingest_too_many_parents_fails(ingest_client: AsyncClient, tmp_path: Path):
    """26 prompts exceeds MAX_PARENTS_PER_INGEST=25 -> synchronous HTTP 422."""
    md_file = tmp_path / "too_many.md"
    _make_md(md_file, n_prompts=26)

    resp = await ingest_client.post(
        "/api/v1/ingest", json={"paths": [str(md_file)]}
    )
    # Pre-validation now runs synchronously before the job is created,
    # so >25 prompts returns 422 immediately rather than an async job failure.
    assert resp.status_code == 422
    body = resp.json()
    detail = body.get("detail") or {}
    error_code = detail.get("code", "").lower()
    error_msg = detail.get("message", "").lower()
    assert "too_many_parents" in error_code or "too many" in error_msg


@pytest.mark.asyncio
async def test_ingest_duplicate_skipped(ingest_client: AsyncClient, tmp_path: Path):
    """Ingesting the same file twice must not create duplicate Template rows."""
    md_file = tmp_path / "dedup.md"
    _make_md(md_file, n_prompts=2)

    async def _ingest_and_wait():
        with (
            patch(
                "app.services.ingest_job.embed_batch",
                side_effect=lambda texts: np.zeros((len(texts), 384)),
            ),
            patch(
                "app.services.ingest_job.get_or_create_collection",
                return_value=MagicMock(),
            ),
            patch("app.services.ingest_job.insert_chunks", return_value=None),
        ):
            resp = await ingest_client.post(
                "/api/v1/ingest", json={"paths": [str(md_file)]}
            )
            assert resp.status_code == 202
            job_id = resp.json()["job_id"]
            return await _poll_job(ingest_client, job_id)

    job1 = await _ingest_and_wait()
    assert job1["status"] == "completed"

    async with TestSessionLocal() as session:
        count_after_first = await session.scalar(
            select(func.count()).select_from(Template)
        )
    assert count_after_first == 2

    job2 = await _ingest_and_wait()
    assert job2["status"] == "completed"

    async with TestSessionLocal() as session:
        count_after_second = await session.scalar(
            select(func.count()).select_from(Template)
        )
    # No new rows — content_hash deduplication keeps the count at 2
    assert count_after_second == 2
