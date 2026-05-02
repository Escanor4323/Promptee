"""Models API endpoints for Promptee.

Provides endpoints to list and register AI models for tracking execution
and preference analysis.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.db.sqlite import async_session
from backend.app.models.models import Model

logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])


class ModelRequest(BaseModel):
    """Request body for POST /api/v1/models."""

    name: str = Field(..., description="Model name (e.g., claude-opus-4-7)")
    type: str = Field(..., description="Model type (e.g., claude, gpt, custom)")


class ModelResponse(BaseModel):
    """Response body for GET/POST /api/v1/models."""

    id: int
    name: str
    type: str
    created_at: str


@router.get("/models", response_model=list[ModelResponse])
async def list_models() -> list[ModelResponse]:
    """List all registered models."""
    async with async_session() as session:
        result = await session.execute(select(Model).order_by(Model.created_at.desc()))
        models = result.scalars().all()
        return [
            ModelResponse(
                id=m.id,
                name=m.name,
                type=m.type,
                created_at=str(m.created_at),
            )
            for m in models
        ]


@router.post("/models", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def register_model(body: ModelRequest) -> ModelResponse:
    """Register a new model.

    Returns 409 Conflict if model name already exists.
    """
    async with async_session() as session:
        # Check if model already exists
        result = await session.execute(select(Model).where(Model.name == body.name))
        existing = result.scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Model with name '{body.name}' already exists",
            )

        # Create new model
        model = Model(name=body.name, type=body.type)
        session.add(model)
        await session.flush()
        await session.commit()

        logger.info("Registered model: id=%d name=%s type=%s", model.id, model.name, model.type)

        return ModelResponse(
            id=model.id,
            name=model.name,
            type=model.type,
            created_at=str(model.created_at),
        )
