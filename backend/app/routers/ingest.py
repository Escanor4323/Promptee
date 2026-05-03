"""POST /api/v1/ingest endpoint for document ingestion pipeline.

Ingests markdown/PDF prompt templates into Milvus AND creates corresponding
SQLite Template records with content_hash deduplication.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.db.milvus import get_or_create_collection, insert_chunks
from app.db.sqlite import async_session
from app.models.templates import Template
from app.schemas import IngestRequest, IngestResponse
from app.services.chunker import Chunk, chunk_file_auto
from app.services.embedder import embed_batch
from app.services.path_resolver import get_path_resolver, PathResolutionError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])


def _collect_file_paths(paths: list[str], directory: str | None, resolve: Callable) -> list[Path]:
    """Resolve and validate all markdown file paths from the request."""
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
    if directory is not None:
        try:
            dir_path = resolve(directory).container_path
        except PathResolutionError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid directory path {directory}: {exc}")
        if not dir_path.exists():
            raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")
        if not dir_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {directory}")
        md_files = sorted(dir_path.glob("*.md"))
        pdf_files = sorted(dir_path.glob("*.pdf"))
        all_files = md_files + pdf_files
        logger.info("Globbed %d *.md + %d *.pdf files from directory: %s", len(md_files), len(pdf_files), directory)
        file_paths.extend(all_files)
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for fp in file_paths:
        if fp.resolve() not in seen:
            seen.add(fp.resolve())
            unique_paths.append(fp)
    return unique_paths


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(
    request: IngestRequest,
    resolve: Callable = Depends(get_path_resolver),
) -> IngestResponse:
    """Ingest markdown prompt templates into the vector database.

    Pipeline: chunk -> embed -> create SQLite Templates -> insert Milvus -> backfill milvus_id.
    Each chunk produces one Milvus vector AND one SQLite Template row,
    linked by template_id stored in Milvus metadata.
    """
    if not request.paths and not request.directory:
        raise HTTPException(status_code=400, detail="At least one of 'paths' or 'directory' must be provided")
    file_paths = _collect_file_paths(request.paths, request.directory, resolve)
    if not file_paths:
        raise HTTPException(status_code=400, detail="No supported files found (.md, .pdf)")
    all_chunks: list[Chunk] = []
    for fp in file_paths:
        try:
            chunks = chunk_file_auto(str(fp))
            logger.info("Extracted %d chunks from %s", len(chunks), fp)
            all_chunks.extend(chunks)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read file {fp}: {exc}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid file {fp}: {exc}")
    if not all_chunks:
        return IngestResponse(ingested=0, titles=[])

    embed_texts = [f"{c.title} {c.objective}".strip() for c in all_chunks]
    try:
        embeddings = embed_batch(embed_texts)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {exc}")

    # Create SQLite Template records first to get template_ids
    # Compute content hashes and check for duplicates
    template_ids: list[int] = []
    async with async_session() as session:
        for chunk in all_chunks:
            content_hash = hashlib.sha256(chunk.full_text.encode()).hexdigest()
            # Check if this content already exists (deduplication)
            result = await session.execute(
                select(Template).where(Template.content_hash == content_hash)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                logger.info("Skipping duplicate content (hash=%s, title=%s)", content_hash, chunk.title)
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

    if len(template_ids) != len(all_chunks):
        raise HTTPException(status_code=500, detail="Failed to create all SQLite Template records")

    try:
        get_or_create_collection()
        milvus_ids = insert_chunks(
            all_chunks,
            [embeddings[i] for i in range(len(all_chunks))],
            template_ids,
        )
    except Exception as exc:
        logger.error("Milvus insertion failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Milvus insertion failed: {exc}")

    # Update SQLite Template rows with their Milvus IDs
    async with async_session() as session:
        for template_id, milvus_id in zip(template_ids, milvus_ids):
            result = await session.execute(
                select(Template).where(Template.id == template_id)
            )
            template = result.scalar_one_or_none()
            if template is not None:
                template.milvus_id = milvus_id
            await session.flush()

    titles = [c.title for c in all_chunks]
    logger.info("Ingested %d chunks with %d SQLite Template records", len(all_chunks), len(template_ids))
    return IngestResponse(ingested=len(all_chunks), titles=titles)
