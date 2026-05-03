"""FastAPI application factory for Promptee (Daedalus)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.milvus import get_or_create_collection
from app.db.sqlite import init_db
# Import all models to ensure tables are created during init_db()
from app.models import Execution, Feedback, Model, ModelPreference, Template  # noqa: F401
from app.routers.addons import router as addons_router
from app.routers.health import router as health_router
from app.routers.ingest import router as ingest_router
from app.routers.models import router as models_router
from app.routers.preferences import router as preferences_router
from app.routers.recommend import router as recommend_router
from app.routers.telemetry import router as telemetry_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.info("Promptee backend starting on %s:%d", settings.fastapi_host, settings.fastapi_port)
    await init_db()
    try:
        get_or_create_collection()
        logger.info("Milvus collection initialized")
    except Exception as e:
        logger.error("Failed to initialize Milvus collection: %s", e)
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
    app.include_router(models_router, prefix="/api/v1", tags=["models"])
    app.include_router(preferences_router, prefix="/api/v1", tags=["preferences"])
    app.include_router(recommend_router, prefix="/api/v1", tags=["recommend"])
    app.include_router(telemetry_router, prefix="/api/v1", tags=["telemetry"])
    return app


app = create_app()
