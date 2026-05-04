"""POST /api/v1/ingest endpoint for document ingestion pipeline.

Validates the request synchronously and enqueues an async background job.
Returns HTTP 202 with a job_id immediately; poll /api/v1/jobs/{job_id} for status.
"""

import asyncio
import logging
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import JSONResponse

from app.schemas import IngestRequest, JobEnqueueResponse
from app.services.chunker import chunk_file_auto
from app.services.ingest_validator import IngestValidationError, validate_parents
from app.services.path_resolver import get_path_resolver, PathResolutionError
import app.services.job_runner as job_runner
from app.services.ingest_job import run_ingest_job
from app.services.job_runner import ProgressEmitter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])

# Module-level task set — holds strong references to prevent GC of running tasks
_active_tasks: set[asyncio.Task] = set()


def _collect_file_paths(
    paths: list[str],
    directory: str | None,
    resolve: Callable,
) -> tuple[list[Path], str | None]:
    """Resolve and validate all markdown/PDF file paths from the request.

    Returns a tuple of (unique resolved Path list, resolved directory string or None).
    Raises HTTPException on invalid inputs.
    Runs synchronously before the job is enqueued so errors surface immediately as 400.
    """
    file_paths: list[Path] = []
    for p in paths:
        try:
            path = resolve(p).container_path
        except PathResolutionError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid path {p}: {exc}")
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {p}")
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {p}")
        file_paths.append(path)

    resolved_directory: str | None = None
    if directory is not None:
        try:
            dir_path = resolve(directory).container_path
        except PathResolutionError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid directory path {directory}: {exc}")
        if not dir_path.exists():
            raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")
        if not dir_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {directory}")
        resolved_directory = str(dir_path)

    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for fp in file_paths:
        if fp.resolve() not in seen:
            seen.add(fp.resolve())
            unique_paths.append(fp)

    return unique_paths, resolved_directory


@router.post("/ingest", response_model=JobEnqueueResponse, status_code=202)
async def ingest_documents(
    request: IngestRequest,
    resolve: Callable = Depends(get_path_resolver),
) -> JSONResponse:
    """Enqueue an async ingest job and return immediately with a job_id.

    Validation errors (missing files, invalid paths) are returned synchronously
    as 400/422. The actual ingestion pipeline runs in the background.

    Poll GET /api/v1/jobs/{job_id} for status and results.
    """
    if not request.paths and not request.directory:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'paths' or 'directory' must be provided",
        )

    # Validate paths synchronously — return 400 immediately on bad input
    file_paths, resolved_directory = _collect_file_paths(
        request.paths, request.directory, resolve
    )

    # Pre-validate: parse documents and check parent count synchronously.
    # This enables proper HTTP 422 responses instead of async job failures
    # when a document exceeds MAX_PARENTS_PER_INGEST (25 prompts).
    # Enumerate both explicit paths AND directory files so the 422 gate
    # fires for directory-based ingests too.
    all_chunks = []
    pre_validate_paths: list[Path] = list(file_paths)
    if resolved_directory is not None:
        dir_path = Path(resolved_directory)
        pre_validate_paths.extend(sorted(dir_path.glob("*.md")))
        pre_validate_paths.extend(sorted(dir_path.glob("*.pdf")))

    for fp in pre_validate_paths:
        try:
            chunks = await asyncio.to_thread(chunk_file_auto, str(fp))
            all_chunks.extend(chunks)
        except Exception:
            pass  # file parsing errors are handled inside the job with better context

    try:
        if all_chunks:
            validate_parents(all_chunks)
    except IngestValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": exc.error.code,
                "message": exc.error.message,
                "detail": exc.error.detail,
            },
        )

    # Create the job record in DB
    job_id = await job_runner.create_job(
        "ingest",
        {"paths": [str(p) for p in file_paths], "directory": resolved_directory},
    )

    emit = ProgressEmitter(job_id=job_id)

    # Schedule background task; hold strong reference to prevent premature GC
    task = asyncio.create_task(
        run_ingest_job(
            job_id=job_id,
            paths=[str(p) for p in file_paths],
            directory=resolved_directory,
            emit=emit,
        )
    )
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)

    logger.info("Enqueued ingest job %s (%d file paths)", job_id, len(file_paths))
    return JSONResponse(
        status_code=202,
        content=JobEnqueueResponse(
            job_id=job_id,
            status="pending",
            status_url=f"/api/v1/jobs/{job_id}",
        ).model_dump(),
    )
