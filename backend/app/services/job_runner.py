"""Async job runner utilities for Promptee background jobs.

Provides:
- ProgressEmitter: debounced DB progress writer (dataclass, per-job)
- create_job: insert a new Job row with status="pending"
- update_progress: debounced progress update via ProgressEmitter
- mark_completed: set status="completed" with result JSON
- mark_failed: set status="failed" with error string
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.db.sqlite import async_session
from app.models.jobs import Job

logger = logging.getLogger(__name__)

# Module-level debounce state: job_id -> last DB write timestamp (seconds)
_last_update_time: dict[str, float] = {}


@dataclass
class ProgressEmitter:
    """Debounced progress emitter that writes job progress to the DB.

    Attributes:
        job_id: The job UUID to update.
        debounce_ms: Minimum milliseconds between DB writes (default 250).
    """

    job_id: str
    debounce_ms: int = 250

    # Internal mutable state — not part of public interface
    _pending_step: Optional[str] = field(default=None, init=False, repr=False)
    _pending_completed: int = field(default=0, init=False, repr=False)
    _pending_total: int = field(default=0, init=False, repr=False)

    async def emit(self, step: str, completed: int, total: int) -> None:
        """Update progress, writing to DB only if debounce interval has elapsed.

        Args:
            step: Human-readable current step name (e.g. "chunking").
            completed: Number of completed units.
            total: Total number of units.
        """
        self._pending_step = step
        self._pending_completed = completed
        self._pending_total = total

        last = _last_update_time.get(self.job_id, 0.0)
        if (time.time() - last) < (self.debounce_ms / 1000.0):
            return

        await self._write(step, completed, total)

    async def flush(self) -> None:
        """Force a final DB write regardless of debounce state."""
        if self._pending_step is not None:
            await self._write(self._pending_step, self._pending_completed, self._pending_total)

    async def _write(self, step: str, completed: int, total: int) -> None:
        """Write current progress to the DB and update debounce timestamp."""
        pct = (completed / total * 100.0) if total > 0 else 0.0
        _last_update_time[self.job_id] = time.time()

        async with async_session() as session:
            result = await session.execute(select(Job).where(Job.id == self.job_id))
            job = result.scalar_one_or_none()
            if job is None:
                logger.warning("ProgressEmitter: job %s not found, skipping write", self.job_id)
                return
            job.current_step = step
            job.completed_steps = completed
            job.total_steps = total
            job.progress_pct = pct
            job.status = "processing"
            if job.started_at is None:
                job.started_at = datetime.utcnow()

        logger.debug(
            "Job %s progress: %s %d/%d (%.1f%%)",
            self.job_id, step, completed, total, pct,
        )


async def create_job(kind: str, params: dict) -> str:
    """Insert a new Job row with status='pending' and return its job_id.

    Args:
        kind: Job kind, one of JOB_KINDS (e.g. "ingest", "docling_warmup").
        params: Original request parameters to store as JSON.

    Returns:
        The generated job_id (32-char UUID hex string, no hyphens).
    """
    job_id = uuid.uuid4().hex
    async with async_session() as session:
        job = Job(
            id=job_id,
            kind=kind,
            status="pending",
            progress_pct=0.0,
            current_step="pending",
            completed_steps=0,
            total_steps=None,
            params_json=json.dumps(params),
        )
        session.add(job)

    logger.info("Created job %s (kind=%s)", job_id, kind)
    return job_id


async def update_progress(job_id: str, step: str, completed: int, total: int) -> None:
    """Update job progress via a one-off ProgressEmitter (debounced).

    Convenience wrapper for callers that don't hold a ProgressEmitter instance.
    """
    emitter = ProgressEmitter(job_id=job_id)
    await emitter.emit(step, completed, total)


async def mark_completed(job_id: str, result: dict) -> None:
    """Set job status to 'completed' with serialized result.

    Args:
        job_id: The job to mark complete.
        result: Dict representation of IngestResponse (from .model_dump()).
    """
    async with async_session() as session:
        res = await session.execute(select(Job).where(Job.id == job_id))
        job = res.scalar_one_or_none()
        if job is None:
            logger.warning("mark_completed: job %s not found", job_id)
            return
        job.status = "completed"
        job.progress_pct = 100.0
        job.result_json = json.dumps(result)
        job.completed_at = datetime.utcnow()

    _last_update_time.pop(job_id, None)
    logger.info("Job %s completed", job_id)


async def mark_failed(job_id: str, error: str) -> None:
    """Set job status to 'failed' with an error message.

    Args:
        job_id: The job to mark as failed.
        error: Human-readable error description.
    """
    async with async_session() as session:
        res = await session.execute(select(Job).where(Job.id == job_id))
        job = res.scalar_one_or_none()
        if job is None:
            logger.warning("mark_failed: job %s not found", job_id)
            return
        job.status = "failed"
        job.error = error
        job.completed_at = datetime.utcnow()

    _last_update_time.pop(job_id, None)
    logger.error("Job %s failed: %s", job_id, error)
