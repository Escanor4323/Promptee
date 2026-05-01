"""Hybrid Reranking Algorithm for Promptee.

Intercepts Top-N semantic results from Milvus, queries SQLite for historical
telemetry data, and computes a weighted hybrid score to boost high-quality
templates into the recommendation set.

Mathematical Formula
--------------------
    hybrid_score = alpha * semantic_score + beta * quality_boost + gamma * popularity_boost

    Default weights (balanced):
        alpha = 0.4  -- semantic similarity weight
        beta  = 0.4  -- historical quality weight
        gamma = 0.2  -- popularity weight

    tradeoff_preference weight adjustments:
        "speed":    alpha=0.3, beta=0.2, gamma=0.5
        "cost":     alpha=0.3, beta=0.2, gamma=0.5
        "quality":  alpha=0.3, beta=0.6, gamma=0.1
        "balanced": alpha=0.4, beta=0.4, gamma=0.2

    Component scores (all normalized 0-1):
        semantic_score   = Milvus COSINE distance (higher = more similar)
        quality_boost    = avg(quality_score) / 5.0  (5-star = 1.0)
                           Default 0.5 if no historical feedback exists.
        popularity_boost = log(1 + execution_count) / log(1 + max_all_executions)
                           Default 0.0 if no executions exist for the template.
"""

import logging
import math
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.executions import Execution
from backend.app.models.feedback import Feedback
from backend.app.models.templates import Template

logger = logging.getLogger(__name__)

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "speed": {"alpha": 0.3, "beta": 0.2, "gamma": 0.5},
    "cost": {"alpha": 0.3, "beta": 0.2, "gamma": 0.5},
    "quality": {"alpha": 0.3, "beta": 0.6, "gamma": 0.1},
    "balanced": {"alpha": 0.4, "beta": 0.4, "gamma": 0.2},
}

QUALITY_DEFAULT: float = 0.5
POPULARITY_DEFAULT: float = 0.0


async def _get_template_stats(
    template_id: int,
    session: AsyncSession,
) -> tuple[float, int]:
    """Return (avg_quality_score, execution_count) for a template.

    Returns (QUALITY_DEFAULT, 0) when no data exists.
    """
    avg_score: Optional[float] = None
    exec_count: int = 0

    # Average quality score across all feedback for this template
    quality_stmt = (
        select(func.avg(Feedback.quality_score))
        .join(Execution, Execution.id == Feedback.execution_id)
        .where(Execution.template_id == template_id)
    )
    result = await session.execute(quality_stmt)
    avg_score = result.scalar_one_or_none()

    # Execution count
    count_stmt = (
        select(func.count())
        .select_from(Execution)
        .where(Execution.template_id == template_id)
    )
    result = await session.execute(count_stmt)
    exec_count = result.scalar_one() or 0

    quality = (float(avg_score) / 5.0) if avg_score is not None else QUALITY_DEFAULT
    return quality, exec_count


async def rerank(
    results: list[dict],
    tradeoff_preference: str,
    session: AsyncSession,
    top_k: int = 5,
) -> list[dict]:
    """Rerank Milvus search results using hybrid scoring.

    Args:
        results: List of dicts from Milvus search with keys:
                 id, title, objective, full_text, variables, score.
        tradeoff_preference: One of speed|cost|quality|balanced.
        session: Active AsyncSession for SQLite queries.
        top_k: Number of results to return after reranking.

    Returns:
        Top-k results sorted by hybrid_score (descending), each augmented
        with a ``hybrid_score`` key.
    """
    weights = WEIGHT_PROFILES.get(tradeoff_preference, WEIGHT_PROFILES["balanced"])
    alpha = weights["alpha"]
    beta = weights["beta"]
    gamma = weights["gamma"]

    if not results:
        return []

    # Gather stats for all templates in one pass
    stats: dict[int, tuple[float, int]] = {}
    for r in results:
        tid = r.get("template_id", 0)
        quality, count = await _get_template_stats(tid, session)
        stats[tid] = (quality, count)

    # Find max execution count for popularity normalization
    max_exec = max((stats[r.get("template_id", 0)][1] for r in results), default=1)
    if max_exec == 0:
        max_exec = 1

    reranked: list[dict] = []
    for r in results:
        tid = r.get("template_id", 0)
        quality_boost, exec_count = stats.get(tid, (QUALITY_DEFAULT, 0))

        semantic_score: float = r.get("score", 0.0)

        popularity_boost: float = (
            math.log(1 + exec_count) / math.log(1 + max_exec)
            if exec_count > 0
            else POPULARITY_DEFAULT
        )

        hybrid = (
            alpha * semantic_score
            + beta * quality_boost
            + gamma * popularity_boost
        )

        reranked.append({**r, "hybrid_score": hybrid})

    reranked.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return reranked[:top_k]
