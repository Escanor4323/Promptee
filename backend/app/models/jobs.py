"""Job SQLAlchemy model.

Tracks async background jobs (e.g., ingest, docling_warmup) including
progress, status, errors, and results.
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.db.sqlite import Base

# Immutable enum value containers (follows coding-style.md immutability)
JOB_KINDS: tuple[str, ...] = ("ingest", "docling_warmup")
JOB_STATUSES: tuple[str, ...] = ("pending", "processing", "completed", "failed", "cancelled")


class Job(Base):
    """SQLAlchemy model for the ``jobs`` table.

    Tracks progress and outcome of async background jobs.
    Mutable (frozen=False) because status/progress are updated in-place
    by the job runner as the job progresses.
    """

    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    kind = Column(String(32), nullable=False)  # see JOB_KINDS
    status = Column(String(32), nullable=False, default="pending")  # see JOB_STATUSES
    progress_pct = Column(Float, nullable=False, default=0.0)
    current_step = Column(String(128), nullable=False, default="pending")
    total_steps = Column(Integer, nullable=True)
    completed_steps = Column(Integer, nullable=False, default=0)
    error = Column(String, nullable=True)
    result_json = Column(String, nullable=True)   # IngestResponse JSON on success
    params_json = Column(String, nullable=True)   # original request params JSON

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Job id={self.id} kind={self.kind!r} status={self.status!r} progress={self.progress_pct:.1f}%>"
