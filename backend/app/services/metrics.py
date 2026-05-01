"""Metric computation service for Promptee.

Provides deterministic functions and an async database-backed function
for computing the three tradeoff scores: speed, cost, and quality.

Scoring formulas
----------------
- speed  = 1.0 / (1.0 + (latency_ms / 1000.0) + ((input_tokens + output_tokens) / 10000.0))
- cost   = 1.0 / (1.0 + ((input_tokens + output_tokens) / 5000.0))
- quality = avg(feedback.quality_score) / 5.0  -- 0.5 when no feedback exists
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.executions import Execution
from backend.app.models.feedback import Feedback

logger = logging.getLogger(__name__)


def compute_speed_score(
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Compute a normalized speed tradeoff score (0.0-1.0).

    Lower latency and fewer tokens produce a higher score.

    Formula::

        speed = 1.0 / (1.0 + (latency_ms / 1000.0) + ((input_tokens + output_tokens) / 10000.0))

    Args:
        latency_ms: Execution latency in milliseconds.
        input_tokens: Number of prompt tokens sent.
        output_tokens: Number of completion tokens received.

    Returns:
        Float in range 0.0 to 1.0 (approaches 0 as latency/tokens grow).
    """
    total_tokens: int = input_tokens + output_tokens
    score: float = 1.0 / (
        1.0 + (latency_ms / 1000.0) + (total_tokens / 10000.0)
    )
    logger.debug(
        "compute_speed_score: latency_ms=%.1f tokens=%d -> %.4f",
        latency_ms,
        total_tokens,
        score,
    )
    return float(score)


def compute_cost_score(
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Compute a normalized cost tradeoff score (0.0-1.0).

    Fewer total tokens produce a higher score, reflecting lower API cost.

    Formula::

        cost = 1.0 / (1.0 + ((input_tokens + output_tokens) / 5000.0))

    Args:
        input_tokens: Number of prompt tokens sent.
        output_tokens: Number of completion tokens received.

    Returns:
        Float in range 0.0 to 1.0 (approaches 0 as token count grows).
    """
    total_tokens: int = input_tokens + output_tokens
    score: float = 1.0 / (1.0 + (total_tokens / 5000.0))
    logger.debug(
        "compute_cost_score: tokens=%d -> %.4f",
        total_tokens,
        score,
    )
    return float(score)


async def compute_quality_score(
    template_id: int,
    session: AsyncSession,
) -> float:
    """Compute a normalized quality tradeoff score (0.0-1.0) from feedback.

    Queries the average ``quality_score`` from all Feedback rows linked
    to Executions for the given ``template_id``, then normalizes to 0-1
    by dividing by 5.

    Args:
        template_id: The template whose quality score to compute.
        session: An active ``AsyncSession`` for database access.

    Returns:
        Float in range 0.0 to 1.0.  Returns 0.5 when no feedback exists.
    """
    stmt = (
        select(func.avg(Feedback.quality_score))
        .join(Execution, Execution.id == Feedback.execution_id)
        .where(Execution.template_id == template_id)
    )
    result = await session.execute(stmt)
    avg_score: Optional[float] = result.scalar_one_or_none()

    if avg_score is None:
        logger.debug(
            "compute_quality_score: template_id=%d -> no feedback, using 0.5",
            template_id,
        )
        return 0.5

    normalized: float = float(avg_score) / 5.0
    # Clamp to 0.0-1.0 for safety
    clamped: float = max(0.0, min(1.0, normalized))
    logger.debug(
        "compute_quality_score: template_id=%d avg=%.2f -> %.4f",
        template_id,
        avg_score,
        clamped,
    )
    return clamped
