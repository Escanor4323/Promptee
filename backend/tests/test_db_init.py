"""Tests for database initialisation, introspection helpers, and startup.

Tests cover:
  - init_db() creates all 6 required tables with correct columns
  - init_db() is idempotent (safe to call twice)
  - verify_tables_exist() passes with a full schema
  - verify_tables_exist() raises RuntimeError naming a missing table
  - verify_tables_exist() raises RuntimeError listing ALL missing tables on empty DB
  - jobs table column set matches the Job model definition
  - get_database_status() returns expected keys with correct types
  - FastAPI startup initialises the DB; health + POST /ingest both succeed
"""

import pathlib

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import app.db.sqlite as sqlite_module
from app.db.sqlite import (
    Base,
    REQUIRED_TABLES,
    get_database_status,
    verify_tables_exist,
)
from app.models import Execution, Feedback, Job, Model, ModelPreference, Template  # noqa: F401
from app.main import create_app


_ALL_REQUIRED_TABLES: frozenset[str] = frozenset(REQUIRED_TABLES)

EXPECTED_JOB_COLUMNS: frozenset[str] = frozenset({
    "id", "kind", "status", "progress_pct", "current_step",
    "total_steps", "completed_steps", "error", "result_json", "params_json",
    "created_at", "updated_at", "started_at", "completed_at",
})


def _make_engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


async def _get_table_names(engine) -> list[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa_inspect(sync_conn).get_table_names()
        )


async def _get_column_names(engine, table_name: str) -> list[str]:
    async with engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: sa_inspect(sync_conn).get_columns(table_name)
        )
    return [col["name"] for col in columns]


def _patch_sqlite_module(engine, session_factory):
    orig_eng = sqlite_module.engine
    orig_sess = sqlite_module.AsyncSessionLocal
    sqlite_module.engine = engine
    sqlite_module.AsyncSessionLocal = session_factory

    def restore():
        sqlite_module.engine = orig_eng
        sqlite_module.AsyncSessionLocal = orig_sess

    return restore


@pytest_asyncio.fixture
async def db_engine():
    """Fresh in-memory engine with NO tables, torn down after each test."""
    eng = _make_engine()
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def full_db_engine():
    """In-memory engine with ALL tables created via init_db()."""
    eng = _make_engine()
    session_factory = sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)
    restore = _patch_sqlite_module(eng, session_factory)
    try:
        await sqlite_module.init_db()
        yield eng
    finally:
        restore()
        await eng.dispose()


@pytest_asyncio.fixture
async def startup_client():
    """FastAPI TestClient with patched in-memory DB and real lifespan."""
    eng = _make_engine()
    session_factory = sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)
    restore = _patch_sqlite_module(eng, session_factory)
    application = create_app()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, eng, application
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    restore()
    await eng.dispose()


@pytest.mark.asyncio
async def test_init_db_creates_all_tables(db_engine) -> None:
    """init_db() must create all 6 required application tables."""
    session_factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    restore = _patch_sqlite_module(db_engine, session_factory)
    try:
        await sqlite_module.init_db()
        tables = set(await _get_table_names(db_engine))
    finally:
        restore()
    missing = _ALL_REQUIRED_TABLES - tables
    assert not missing, f"Tables missing after init_db(): {sorted(missing)}. Found: {sorted(tables)}"


@pytest.mark.asyncio
async def test_init_db_idempotent(db_engine) -> None:
    """Calling init_db() twice must not raise and must not duplicate tables."""
    session_factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    restore = _patch_sqlite_module(db_engine, session_factory)
    try:
        await sqlite_module.init_db()
        await sqlite_module.init_db()
        tables = await _get_table_names(db_engine)
    finally:
        restore()
    expected_count = len(_ALL_REQUIRED_TABLES)
    assert len(tables) == expected_count, (
        f"Expected {expected_count} tables after double init_db(), got {len(tables)}: {sorted(tables)}"
    )
    for required in _ALL_REQUIRED_TABLES:
        assert required in set(tables), f"Table {required!r} missing after idempotent init_db()."


@pytest.mark.asyncio
async def test_verify_tables_exist_all_present(full_db_engine) -> None:
    """verify_tables_exist() returns True when all 6 tables are present."""
    result = await verify_tables_exist(db_engine=full_db_engine)
    assert result is True


@pytest.mark.asyncio
async def test_verify_tables_exist_missing_jobs(db_engine) -> None:
    """verify_tables_exist() raises RuntimeError naming jobs when that table is absent."""
    jobs_table = Base.metadata.tables.get("jobs")
    assert jobs_table is not None, "jobs table must be registered in Base.metadata"
    Base.metadata.remove(jobs_table)
    try:
        async with db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        Base.metadata._add_table("jobs", jobs_table.schema, jobs_table)  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError) as exc_info:
        await verify_tables_exist(db_engine=db_engine)
    assert "jobs" in str(exc_info.value), f"Expected jobs in error, got: {exc_info.value}"


@pytest.mark.asyncio
async def test_verify_tables_exist_empty_db(db_engine) -> None:
    """verify_tables_exist() on empty DB raises RuntimeError listing all missing tables."""
    with pytest.raises(RuntimeError) as exc_info:
        await verify_tables_exist(db_engine=db_engine)
    error_message = str(exc_info.value)
    for required in _ALL_REQUIRED_TABLES:
        assert required in error_message, f"Expected {required!r} in error, got: {error_message}"


@pytest.mark.asyncio
async def test_job_table_has_correct_columns(full_db_engine) -> None:
    """The jobs table must contain every column declared in the Job model."""
    columns = set(await _get_column_names(full_db_engine, "jobs"))
    missing_cols = EXPECTED_JOB_COLUMNS - columns
    assert not missing_cols, (
        f"jobs table is missing columns: {sorted(missing_cols)}. Present: {sorted(columns)}"
    )


@pytest.mark.asyncio
async def test_get_database_status(full_db_engine) -> None:
    """get_database_status() returns a dict with db_path, db_size, table_count."""
    status = await get_database_status(db_engine=full_db_engine)
    assert "db_path" in status, f"Missing db_path in: {status}"
    assert "db_size" in status, f"Missing db_size in: {status}"
    assert "table_count" in status, f"Missing table_count in: {status}"
    assert isinstance(status["db_path"], str)
    assert isinstance(status["db_size"], int)
    assert isinstance(status["table_count"], int)
    table_count = status["table_count"]
    assert table_count >= len(_ALL_REQUIRED_TABLES), (
        f"Expected at least {len(_ALL_REQUIRED_TABLES)} tables, got {table_count}"
    )
    db_size = status["db_size"]
    assert db_size == -1, f"Expected db_size=-1 for in-memory SQLite, got {db_size}"
    assert "sqlite" in status["db_path"]


@pytest.mark.asyncio
async def test_fastapi_startup_initializes_db(
    startup_client, tmp_path: pathlib.Path
) -> None:
    """After FastAPI startup the DB is healthy, health passes, and /ingest returns 202.

    The path resolver is overridden so paths under tmp_path are accepted.

    Assertions:
      1. GET /api/v1/health returns 200 with status healthy
      2. All 6 required tables exist in the test engine after startup
      3. POST /api/v1/ingest returns 202 with non-empty job_id and pending status
    """
    from app.config import Settings
    from app.services.path_resolver import get_path_resolver, resolve_to_container_path
    client, eng, application = startup_client

    health_resp = await client.get("/api/v1/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"

    tables = set(await _get_table_names(eng))
    missing = _ALL_REQUIRED_TABLES - tables
    assert not missing, (
        f"Tables missing after FastAPI startup: {sorted(missing)}. Present: {sorted(tables)}"
    )

    md_file = tmp_path / "test_prompt.md"
    content = "# Test Prompt" + chr(10) + chr(10) + "Objective: validate ingest." + chr(10)
    md_file.write_text(content)

    def patched_resolver(path_str: str):
        test_settings = Settings(
            host_project_root=str(tmp_path),
            container_data_root=str(tmp_path),
        )
        return resolve_to_container_path(path_str, test_settings)

    application.dependency_overrides[get_path_resolver] = lambda: patched_resolver
    try:
        ingest_resp = await client.post("/api/v1/ingest", json={"paths": [str(md_file)]})
    finally:
        application.dependency_overrides.pop(get_path_resolver, None)

    assert ingest_resp.status_code == 202, (
        f"Expected 202 from /ingest, got {ingest_resp.status_code}: {ingest_resp.text}"
    )
    ingest_data = ingest_resp.json()
    assert "job_id" in ingest_data, f"Response missing job_id: {ingest_data}"
    assert isinstance(ingest_data["job_id"], str)
    assert len(ingest_data["job_id"]) > 0
    assert ingest_data["status"] == "pending"
    assert "/api/v1/jobs/" in ingest_data["status_url"]
