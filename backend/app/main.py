"""FastAPI application factory for Promptee (Daedalus)."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.milvus import get_or_create_collection
from app.db.sqlite import init_db
# Import all models to ensure tables are created during init_db()
from app.models import Execution, Feedback, Job, Model, ModelPreference, Template  # noqa: F401
from app.routers.addons import router as addons_router
from app.routers.health import router as health_router
from app.routers.ingest import router as ingest_router
from app.routers.jobs import router as jobs_router
from app.routers.models import router as models_router
from app.routers.preferences import router as preferences_router
from app.routers.recommend import router as recommend_router
from app.routers.telemetry import router as telemetry_router
from app.routers.templates import router as templates_router

logger = logging.getLogger(__name__)

# Module-level set keeps strong references to background startup tasks
_startup_tasks: set[asyncio.Task] = set()


async def _warmup_docling_background(job_id: str) -> None:
    """Background task: warm up docling converter and update job status."""
    import app.services.job_runner as job_runner
    from app.services.pdf_parser import _init_docling
    try:
        # _init_docling is synchronous — run in thread to avoid blocking the event loop.
        await asyncio.to_thread(_init_docling)
        await job_runner.mark_completed(job_id, {"ingested": 0, "titles": []})
        logger.info("Docling warmup job %s completed", job_id)
    except Exception as exc:
        logger.warning("Docling warmup job %s failed: %s", job_id, exc)
        await job_runner.mark_failed(job_id, str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.info("Promptee backend starting on %s:%d", settings.fastapi_host, settings.fastapi_port)

    try:
        await init_db()
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.critical("Failed to initialize database on startup: %s", e, exc_info=True)
        raise RuntimeError("Cannot start: database initialization failed") from e

    try:
        get_or_create_collection()
        logger.info("Milvus collection initialized")
    except Exception as e:
        logger.error("Failed to initialize Milvus collection: %s", e)

    if os.getenv("PROMPTEE_PREWARM_DOCLING", "").strip() == "1":
        import app.services.job_runner as job_runner
        warmup_job_id = await job_runner.create_job("docling_warmup", {})
        task = asyncio.create_task(_warmup_docling_background(warmup_job_id))
        _startup_tasks.add(task)
        task.add_done_callback(_startup_tasks.discard)
        logger.info("Scheduled docling warmup job %s", warmup_job_id)

    yield
    logger.info("Promptee backend shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Promptee (Daedalus)",
        description="Local MLOps & RAG CLI backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(addons_router, prefix="/api/v1", tags=["addons"])
    app.include_router(health_router, prefix="/api/v1", tags=["health"])
    app.include_router(ingest_router, prefix="/api/v1", tags=["ingest"])
    app.include_router(jobs_router, prefix="/api/v1", tags=["jobs"])
    app.include_router(models_router, prefix="/api/v1", tags=["models"])
    app.include_router(preferences_router, prefix="/api/v1", tags=["preferences"])
    app.include_router(recommend_router, prefix="/api/v1", tags=["recommend"])
    app.include_router(telemetry_router, prefix="/api/v1", tags=["telemetry"])
    app.include_router(templates_router, prefix="/api/v1", tags=["templates"])
    return app


app = create_app()
