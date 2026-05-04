"""GET /api/v1/jobs/{job_id} endpoint for async job status polling.

Clients poll this endpoint after receiving a 202 from /ingest to check
job progress, retrieve results, or surface errors.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.sqlite import async_session
from app.models.jobs import Job
from app.schemas import IngestResponse, JobStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


def _compute_eta(
    progress_pct: float,
    started_at: Optional[datetime],
) -> Optional[float]:
    """Estimate remaining seconds based on elapsed time and progress percentage.

    Returns None if progress is below 5% (too early to estimate reliably)
    or if started_at is not recorded yet.

    Args:
        progress_pct: Current progress 0.0-100.0.
        started_at: UTC datetime when the job transitioned to "processing".

    Returns:
        Estimated seconds remaining, or None.
    """
    if progress_pct < 5.0 or started_at is None:
        return None
    now = datetime.now(timezone.utc)
    # Ensure started_at is timezone-aware for subtraction
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    elapsed = (now - started_at).total_seconds()
    if elapsed <= 0:
        return None
    return (elapsed * (100.0 - progress_pct)) / progress_pct


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Return the current status of an async background job.

    Args:
        job_id: The 32-char hex UUID returned by POST /ingest.

    Returns:
        JobStatusResponse with progress, step, ETA, and result on completion.

    Raises:
        404 if no job with the given job_id exists.
    """
    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    eta_seconds = _compute_eta(job.progress_pct, job.started_at)

    ingest_result: Optional[IngestResponse] = None
    if job.result_json is not None:
        try:
            ingest_result = IngestResponse(**json.loads(job.result_json))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to deserialize result_json for job %s: %s", job_id, exc)

    return JobStatusResponse(
        job_id=job.id,
        kind=job.kind,
        status=job.status,
        progress_pct=job.progress_pct,
        current_step=job.current_step,
        completed_steps=job.completed_steps,
        total_steps=job.total_steps,
        eta_seconds=eta_seconds,
        error=job.error,
        result=ingest_result,
    )
