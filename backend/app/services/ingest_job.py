"""Background ingest job implementation.

Contains the core async pipeline that runs after the ingest request is
enqueued. Called by the ingest router via asyncio.create_task().

Pipeline steps (emitted as progress):
    resolving_paths -> parsing_files -> chunking ->
    writing_templates -> embedding -> indexing

All CPU-bound / synchronous operations (file chunking, ML embedding, Milvus
inserts) are offloaded to a thread pool via asyncio.to_thread() so the
FastAPI event loop is never blocked and concurrent HTTP requests remain
responsive while a job is in progress.
"""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.db.milvus import get_or_create_collection, insert_chunks
from app.db.sqlite import async_session
from app.models.templates import Template
from app.schemas import IngestResponse
from app.services.child_splitter import ChildChunk, split_children
from app.services.chunker import Chunk, chunk_file_auto
from app.services.embedder import embed_batch
from app.services.ingest_validator import validate_parents, IngestValidationError, MAX_CHILDREN_PER_INGEST, MAX_TOKENS_PER_CHILD
from app.services.job_runner import ProgressEmitter, mark_completed, mark_failed

logger = logging.getLogger(__name__)

# Total named pipeline steps (used for progress percentage)
_PIPELINE_STEPS = (
    "resolving_paths",
    "parsing_files",
    "chunking",
    "writing_templates",
    "embedding",
    "indexing",
)
_TOTAL_STEPS = len(_PIPELINE_STEPS)


async def run_ingest_job(
    job_id: str,
    paths: list[str],
    directory: Optional[str],
    emit: ProgressEmitter,
) -> None:
    """Execute the full ingest pipeline as a background job.

    Emits progress at each stage. On success calls mark_completed;
    on any error calls mark_failed. Always flushes the emitter in finally.

    Args:
        job_id: Job UUID to track progress against.
        paths: List of resolved absolute file path strings.
        directory: Optional directory path string (already resolved by router).
        emit: ProgressEmitter bound to this job_id.
    """
    try:
        await _run_pipeline(job_id, paths, directory, emit)
        # Pipeline completed — discard pending progress so the flush() below
        # does not overwrite the "completed" status written by mark_completed().
        emit._pending_step = None
    except Exception as exc:
        logger.error("Ingest job %s failed: %s", job_id, exc, exc_info=True)
        await mark_failed(job_id, str(exc))
        # Pipeline failed — discard pending progress so the flush() below
        # does not overwrite the "failed" status written by mark_failed().
        emit._pending_step = None
    finally:
        await emit.flush()


async def _run_pipeline(
    job_id: str,
    paths: list[str],
    directory: Optional[str],
    emit: ProgressEmitter,
) -> None:
    """Inner pipeline — raises on error so the outer wrapper can catch cleanly."""
    step_idx = 0

    # --- Step 1: resolving_paths ---
    await emit.emit("resolving_paths", step_idx, _TOTAL_STEPS)
    file_paths: list[Path] = [Path(p) for p in paths]
    if directory is not None:
        dir_path = Path(directory)
        md_files = sorted(dir_path.glob("*.md"))
        pdf_files = sorted(dir_path.glob("*.pdf"))
        file_paths.extend(md_files + pdf_files)

    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for fp in file_paths:
        resolved = fp.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_paths.append(fp)
    file_paths = unique_paths

    if not file_paths:
        raise ValueError("No supported files found (.md, .pdf)")

    step_idx += 1

    # --- Step 2: parsing_files (per-file progress) ---
    await emit.emit("parsing_files", step_idx, _TOTAL_STEPS)
    all_chunks: list[Chunk] = []
    for i, fp in enumerate(file_paths):
        await emit.emit("parsing_files", i, len(file_paths))
        try:
            # chunk_file_auto does synchronous file I/O + regex — run in thread
            # to avoid blocking the event loop during parsing.
            chunks = await asyncio.to_thread(chunk_file_auto, str(fp))
        except OSError as exc:
            raise OSError(f"Failed to read file {fp}: {exc}") from exc
        except ValueError as exc:
            raise ValueError(f"Invalid file {fp}: {exc}") from exc
        logger.info("Extracted %d Parent chunks from %s", len(chunks), fp)
        # #region agent log f0c062
        logger.info("[f0c062] chunk_count=%d titles=%s", len(chunks), [c.title for c in chunks[:5]])
        # #endregion agent log f0c062
        all_chunks.extend(chunks)

    step_idx += 1

    # --- Step 3: chunking validation ---
    await emit.emit("chunking", step_idx, _TOTAL_STEPS)
    if not all_chunks:
        await mark_completed(job_id, IngestResponse(ingested=0, titles=[]).model_dump())
        return

    try:
        validate_parents(all_chunks)
    except IngestValidationError as exc:
        raise ValueError(f"Validation failed: {exc.error.code} — {exc.error.message}") from exc

    step_idx += 1

    # --- Step 4: writing_templates (SQLite) ---
    await emit.emit("writing_templates", step_idx, _TOTAL_STEPS)
    template_ids: list[int] = []
    created_template_ids: list[int] = []  # track newly created rows for rollback

    async with async_session() as session:
        for chunk in all_chunks:
            content_hash = hashlib.sha256(chunk.full_text.encode()).hexdigest()
            result = await session.execute(
                select(Template).where(Template.content_hash == content_hash)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                logger.info("Skipping duplicate (hash=%s, title=%s)", content_hash, chunk.title)
                template_ids.append(existing.id)
                continue

            template = Template(
                milvus_id=None,
                title=chunk.title,
                objective=chunk.objective,
                variables=json.dumps(chunk.variables),
                full_text=chunk.full_text,
                content_hash=content_hash,
            )
            session.add(template)
            await session.flush()
            template_ids.append(template.id)
            created_template_ids.append(template.id)

    if len(template_ids) != len(all_chunks):
        raise RuntimeError("Failed to create all SQLite Template records")

    step_idx += 1

    # --- Step 5: embedding ---
    await emit.emit("embedding", step_idx, _TOTAL_STEPS)

    # Split each parent chunk into overlapping child chunks for dense retrieval.
    # split_children is CPU-bound (tiktoken) — run in thread.
    child_texts: list[str] = []
    child_template_ids: list[int] = []
    chunk_indices: list[int] = []
    token_counts: list[int] = []
    parent_titles: list[str] = []

    for parent_chunk, t_id in zip(all_chunks, template_ids):
        children: tuple[ChildChunk, ...] = await asyncio.to_thread(
            split_children,
            parent_chunk.full_text,
            parent_title=parent_chunk.title,
        )
        for child in children:
            child_texts.append(child.text)
            child_template_ids.append(t_id)
            chunk_indices.append(child.chunk_index)
            token_counts.append(child.token_count)
            parent_titles.append(parent_chunk.title)

    # Inline child validation (validate_children requires .children on parents,
    # which Chunk doesn't carry — validate the flat child list directly instead).
    if not child_texts:
        raise ValueError("No child chunks generated — ensure file has prompt content")

    if len(child_texts) > MAX_CHILDREN_PER_INGEST:
        raise ValueError(
            f"Too many child chunks: {len(child_texts)} exceeds limit {MAX_CHILDREN_PER_INGEST}"
        )

    for i, (text, token_count) in enumerate(zip(child_texts, token_counts)):
        if not text or not text.strip():
            raise ValueError(f"Child chunk #{i} has empty text")
        if token_count > MAX_TOKENS_PER_CHILD:
            raise ValueError(
                f"Child chunk #{i} exceeds {MAX_TOKENS_PER_CHILD} tokens ({token_count})"
            )

    try:
        # embed_batch runs the sentence-transformer model — CPU-intensive and
        # potentially takes seconds. Offload to a thread so the event loop
        # stays free to serve other HTTP requests (e.g. concurrent /add calls).
        embeddings = await asyncio.to_thread(embed_batch, child_texts)
    except RuntimeError as exc:
        raise RuntimeError(f"Embedding generation failed: {exc}") from exc

    step_idx += 1

    # --- Step 6: indexing (Milvus) ---
    await emit.emit("indexing", step_idx, _TOTAL_STEPS)
    try:
        # Both Milvus calls use a synchronous SDK — offload to thread to avoid
        # blocking the event loop during network I/O with the Milvus server.
        await asyncio.to_thread(get_or_create_collection)
        await asyncio.to_thread(
            insert_chunks,
            child_texts=child_texts,
            embeddings=embeddings,
            template_ids=child_template_ids,
            chunk_indices=chunk_indices,
            token_counts=token_counts,
            parent_titles=parent_titles,
        )
    except Exception as exc:
        logger.error(
            "Milvus insertion failed, rolling back %d templates: %s",
            len(created_template_ids), exc,
        )
        await _rollback_templates(created_template_ids)
        raise RuntimeError(f"Milvus insertion failed: {exc}") from exc

    titles = [c.title for c in all_chunks]
    logger.info("Ingested %d Parent chunks and %d Child vectors.", len(all_chunks), len(child_texts))
    await mark_completed(
        job_id,
        IngestResponse(ingested=len(all_chunks), titles=titles).model_dump(),
    )


async def _rollback_templates(template_ids: list[int]) -> None:
    """Delete SQLite Template rows created in this job on Milvus failure.

    Args:
        template_ids: List of Template.id values created in this job run.
    """
    if not template_ids:
        return
    try:
        async with async_session() as session:
            for t_id in template_ids:
                result = await session.execute(select(Template).where(Template.id == t_id))
                template = result.scalar_one_or_none()
                if template is not None:
                    await session.delete(template)
        logger.info("Rolled back %d Template rows after Milvus failure", len(template_ids))
    except Exception as exc:
        logger.error("Rollback failed for template_ids=%s: %s", template_ids, exc)
