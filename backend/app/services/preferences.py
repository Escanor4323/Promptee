"""Preference service for model performance aggregation.

Handles upserting model preferences by computing fresh aggregates from
execution and feedback tables.
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.executions import Execution
from app.models.feedback import Feedback
from app.models.preferences import ModelPreference

logger = logging.getLogger(__name__)


async def upsert_model_preference(
    session: AsyncSession,
    template_id: int,
    model_id: str,
    addon_mode: Optional[str],
) -> ModelPreference:
    """Upsert a model preference record by recomputing aggregates.

    Fetches all executions and feedback for the given template/model/addon_mode
    combination, computes avg_quality_score and execution_count, and creates or
    updates the ModelPreference record.

    Args:
        session: AsyncSession for database operations
        template_id: Template ID
        model_id: Model ID (e.g., "claude-opus-4-7")
        addon_mode: Addon mode (e.g., "speed", "quality", "cost", "balanced") or None

    Returns:
        The created or updated ModelPreference record
    """
    # Count executions for this template/model/addon_mode
    count_stmt = select(func.count(Execution.id)).where(
        Execution.template_id == template_id,
        Execution.model_id == model_id,
        Execution.addon_mode == addon_mode,
    )
    count_result = await session.execute(count_stmt)
    execution_count = count_result.scalar() or 0

    # Compute average quality score from feedback on these executions
    quality_stmt = select(func.avg(Feedback.quality_score)).join(
        Execution,
        Feedback.execution_id == Execution.id,
    ).where(
        Execution.template_id == template_id,
        Execution.model_id == model_id,
        Execution.addon_mode == addon_mode,
    )
    quality_result = await session.execute(quality_stmt)
    avg_quality = quality_result.scalar()
    avg_quality_score = float(avg_quality) if avg_quality else 0.0

    # Upsert ModelPreference
    # Try to find existing preference
    pref_stmt = select(ModelPreference).where(
        ModelPreference.template_id == template_id,
        ModelPreference.model_id == model_id,
        ModelPreference.addon_mode == addon_mode,
    )
    pref_result = await session.execute(pref_stmt)
    existing_pref = pref_result.scalar_one_or_none()

    if existing_pref:
        # Update existing preference
        existing_pref.avg_quality_score = avg_quality_score
        existing_pref.execution_count = execution_count
        session.add(existing_pref)
        logger.info(
            "Updated ModelPreference: template_id=%d model_id=%s addon_mode=%s "
            "count=%d avg_quality=%.2f",
            template_id,
            model_id,
            addon_mode,
            execution_count,
            avg_quality_score,
        )
        return existing_pref
    else:
        # Create new preference
        pref = ModelPreference(
            template_id=template_id,
            model_id=model_id,
            addon_mode=addon_mode,
            avg_quality_score=avg_quality_score,
            execution_count=execution_count,
        )
        session.add(pref)
        logger.info(
            "Created ModelPreference: template_id=%d model_id=%s addon_mode=%s "
            "count=%d avg_quality=%.2f",
            template_id,
            model_id,
            addon_mode,
            execution_count,
            avg_quality_score,
        )
        return pref
