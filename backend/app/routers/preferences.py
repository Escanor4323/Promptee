"""Model Preferences API endpoints for Promptee.

Provides endpoints to query aggregated model performance metrics
across template-addon combinations.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.db.sqlite import async_session
from app.models.preferences import ModelPreference
from app.models.templates import Template

logger = logging.getLogger(__name__)

router = APIRouter(tags=["preferences"])


class PreferenceItem(BaseModel):
    """A model preference entry for a template-addon combination."""

    model_id: str
    addon_mode: str | None
    avg_quality_score: float
    execution_count: int


class PreferencesResponse(BaseModel):
    """Response body for GET /api/v1/preferences/{template_id}."""

    template_id: int
    preferences: list[PreferenceItem]


@router.get(
    "/preferences/{template_id}",
    response_model=PreferencesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_template_preferences(template_id: int) -> PreferencesResponse:
    """Get model preferences for a specific template.

    Returns aggregated quality scores and execution counts by model and addon_mode.
    Returns 404 if template does not exist.
    """
    async with async_session() as session:
        # Verify template exists
        template_result = await session.execute(
            select(Template).where(Template.id == template_id)
        )
        template = template_result.scalar_one_or_none()
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template with id={template_id} not found",
            )

        # Query all preferences for this template
        prefs_result = await session.execute(
            select(ModelPreference).where(ModelPreference.template_id == template_id)
        )
        preferences = prefs_result.scalars().all()

        pref_items = [
            PreferenceItem(
                model_id=p.model_id,
                addon_mode=p.addon_mode,
                avg_quality_score=p.avg_quality_score,
                execution_count=p.execution_count,
            )
            for p in preferences
        ]

        logger.info(
            "Fetched preferences for template_id=%d: %d preferences",
            template_id,
            len(pref_items),
        )

        return PreferencesResponse(template_id=template_id, preferences=pref_items)
