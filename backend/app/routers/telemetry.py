"""Telemetry and Feedback API endpoints for Promptee.

Provides two POST endpoints:
- ``/api/v1/telemetry`` -- Record execution telemetry with computed tradeoff scores.
- ``/api/v1/feedback``  -- Record human-in-the-loop quality feedback for an execution.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.sqlite import async_session
from backend.app.models.executions import Execution
from backend.app.models.feedback import Feedback
from backend.app.models.templates import Template
from backend.app.services.metrics import (
    compute_cost_score,
    compute_quality_score,
    compute_speed_score,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telemetry"])


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------


class TelemetryRequest(BaseModel):
    """Request body for POST /api/v1/telemetry."""

    template_id: int = Field(..., description="FK to templates table")
    latency_ms: float = Field(..., ge=0, description="Execution latency in ms")
    input_tokens: int = Field(..., ge=0, description="Prompt tokens sent")
    output_tokens: int = Field(..., ge=0, description="Completion tokens received")
    context_window_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Context window utilization %"
    )
    verbosity: str = Field(
        ..., description="Verbosity level: terse | moderate | verbose"
    )
    addon_mode: Optional[str] = Field(
        None, description="AddOn mode: speed | quality | cost | balanced"
    )

    @field_validator("verbosity")
    @classmethod
    def validate_verbosity(cls, v: str) -> str:
        allowed: set[str] = {"terse", "moderate", "verbose"}
        if v not in allowed:
            raise ValueError(f"verbosity must be one of {allowed}, got '{v}'")
        return v

    @field_validator("addon_mode")
    @classmethod
    def validate_addon_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed: set[str] = {"speed", "quality", "cost", "balanced"}
        if v not in allowed:
            raise ValueError(f"addon_mode must be one of {allowed}, got '{v}'")
        return v


class TelemetryResponse(BaseModel):
    """Response body for POST /api/v1/telemetry."""

    id: int
    template_id: int
    latency_ms: float
    input_tokens: int
    output_tokens: int
    context_window_pct: float
    verbosity: str
    tradeoff_speed: float
    tradeoff_cost: float
    tradeoff_quality: float
    addon_mode: Optional[str]
    executed_at: str

    model_config = ConfigDict(from_attributes=True)


class FeedbackRequest(BaseModel):
    """Request body for POST /api/v1/feedback."""

    execution_id: int = Field(..., description="FK to executions table")
    quality_score: int = Field(
        ..., ge=1, le=5, description="Quality rating 1-5"
    )
    notes: Optional[str] = Field(None, description="Optional free-text notes")


class FeedbackResponse(BaseModel):
    """Response body for POST /api/v1/feedback."""

    id: int
    execution_id: int
    quality_score: int
    notes: Optional[str]
    created_at: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/telemetry",
    response_model=TelemetryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_telemetry(body: TelemetryRequest) -> TelemetryResponse:
    """Record execution telemetry and compute tradeoff scores.

    Validates that the referenced template exists, computes speed and
    cost scores deterministically, computes the quality score from
    historical feedback, and persists the Execution record.
    """
    async with async_session() as session:
        # Verify template exists
        template_result = await session.execute(
            select(Template).where(Template.id == body.template_id)
        )
        template: Optional[Template] = template_result.scalar_one_or_none()
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template with id={body.template_id} not found",
            )

        # Compute tradeoff scores
        speed: float = compute_speed_score(
            latency_ms=body.latency_ms,
            input_tokens=body.input_tokens,
            output_tokens=body.output_tokens,
        )
        cost: float = compute_cost_score(
            input_tokens=body.input_tokens,
            output_tokens=body.output_tokens,
        )
        quality: float = await compute_quality_score(
            template_id=body.template_id,
            session=session,
        )

        # Create Execution record
        execution = Execution(
            template_id=body.template_id,
            latency_ms=body.latency_ms,
            input_tokens=body.input_tokens,
            output_tokens=body.output_tokens,
            context_window_pct=body.context_window_pct,
            verbosity=body.verbosity,
            tradeoff_speed=speed,
            tradeoff_cost=cost,
            tradeoff_quality=quality,
            addon_mode=body.addon_mode,
        )
        session.add(execution)
        await session.flush()

        logger.info(
            "Recorded telemetry: execution_id=%d template_id=%d "
            "speed=%.4f cost=%.4f quality=%.4f",
            execution.id,
            body.template_id,
            speed,
            cost,
            quality,
        )

        return TelemetryResponse(
            id=execution.id,
            template_id=execution.template_id,
            latency_ms=execution.latency_ms,
            input_tokens=execution.input_tokens,
            output_tokens=execution.output_tokens,
            context_window_pct=execution.context_window_pct,
            verbosity=execution.verbosity,
            tradeoff_speed=execution.tradeoff_speed,
            tradeoff_cost=execution.tradeoff_cost,
            tradeoff_quality=execution.tradeoff_quality,
            addon_mode=execution.addon_mode,
            executed_at=str(execution.executed_at),
        )


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """Record human-in-the-loop quality feedback for an execution.

    Validates that the referenced execution exists and that
    ``quality_score`` is in the range 1-5.
    """
    async with async_session() as session:
        # Verify execution exists
        execution_result = await session.execute(
            select(Execution).where(Execution.id == body.execution_id)
        )
        execution: Optional[Execution] = execution_result.scalar_one_or_none()
        if execution is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Execution with id={body.execution_id} not found",
            )

        # Validate quality_score range (Pydantic also enforces, but
        # defensive check aligns with explicit error handling rule)
        if body.quality_score < 1 or body.quality_score > 5:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="quality_score must be between 1 and 5",
            )

        feedback = Feedback(
            execution_id=body.execution_id,
            quality_score=body.quality_score,
            notes=body.notes,
        )
        session.add(feedback)
        await session.flush()

        logger.info(
            "Recorded feedback: feedback_id=%d execution_id=%d score=%d",
            feedback.id,
            body.execution_id,
            body.quality_score,
        )

        return FeedbackResponse(
            id=feedback.id,
            execution_id=feedback.execution_id,
            quality_score=feedback.quality_score,
            notes=feedback.notes,
            created_at=str(feedback.created_at),
        )


@router.get("/summary")
async def get_telemetry_summary():
    """Get aggregated telemetry: execution counts by category and avg quality."""
    from sqlalchemy import func, select

    from backend.app.models.executions import Execution
    from backend.app.models.feedback import Feedback

    async with async_session() as session:
        # Total executions by addon_mode
        stmt = (
            select(Execution.addon_mode, func.count(Execution.id).label("count"))
            .group_by(Execution.addon_mode)
        )
        result = await session.execute(stmt)
        mode_counts = {row[0] or "none": row[1] for row in result.fetchall()}

        # Total executions and avg quality
        stmt = select(func.count(Execution.id), func.avg(Feedback.quality_score))
        stmt = stmt.join(
            Feedback, Feedback.execution_id == Execution.id, isouter=True
        )
        result = await session.execute(stmt)
        total, avg_quality = result.one()

        total = total or 0
        avg_quality = float(avg_quality) if avg_quality else 0.0

        # Calculate percentages
        categories = {"speed": 0, "cost": 0, "quality": 0, "balanced": 0}
        for mode, count in mode_counts.items():
            if mode in categories:
                categories[mode] = count

        percentages = {}
        for cat, count in categories.items():
            percentages[cat] = (
                round(100 * count / total, 1) if total > 0 else 0.0
            )

        return {
            "total_executions": total,
            "avg_quality_score": round(avg_quality, 1),
            "by_category": {
                "speed": categories["speed"],
                "cost": categories["cost"],
                "quality": categories["quality"],
                "balanced": categories["balanced"],
            },
            "percentages": percentages,
        }
