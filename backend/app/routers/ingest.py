"""POST /api/v1/ingest endpoint for document ingestion pipeline.

Ingests markdown prompt templates into Milvus AND creates corresponding
SQLite Template records so that telemetry/feedback can reference them.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.app.db.milvus import get_or_create_collection, insert_chunks
from backend.app.db.sqlite import async_session
from backend.app.models.templates import Template
from backend.app.schemas import IngestRequest, IngestResponse
from backend.app.services.chunker import Chunk, chunk_file
from backend.app.services.embedder import embed_batch

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])


def _collect_file_paths(paths: list[str], directory: str | None) -> list[Path]:
    """Resolve and validate all markdown file paths from the request."""
    file_paths: list[Path] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {p}")
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {p}")
        file_paths.append(path)
    if directory is not None:
        dir_path = Path(directory)
        if not dir_path.exists():
            raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")
        if not dir_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {directory}")
        md_files = sorted(dir_path.glob("*.md"))
        logger.info("Globbed %d *.md files from directory: %s", len(md_files), directory)
        file_paths.extend(md_files)
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for fp in file_paths:
        if fp.resolve() not in seen:
            seen.add(fp.resolve())
            unique_paths.append(fp)
    return unique_paths


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest) -> IngestResponse:
    """Ingest markdown prompt templates into the vector database.

    Pipeline: chunk -> embed -> create SQLite Templates -> insert Milvus -> backfill milvus_id.
    Each chunk produces one Milvus vector AND one SQLite Template row,
    linked by template_id stored in Milvus metadata.
    """
    if not request.paths and not request.directory:
        raise HTTPException(status_code=400, detail="At least one of 'paths' or 'directory' must be provided")
    file_paths = _collect_file_paths(request.paths, request.directory)
    if not file_paths:
        raise HTTPException(status_code=400, detail="No markdown files found")
    all_chunks: list[Chunk] = []
    for fp in file_paths:
        try:
            chunks = chunk_file(str(fp))
            logger.info("Extracted %d chunks from %s", len(chunks), fp)
            all_chunks.extend(chunks)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read file {fp}: {exc}")
    if not all_chunks:
        return IngestResponse(ingested=0, titles=[])

    embed_texts = [f"{c.title} {c.objective}".strip() for c in all_chunks]
    try:
        embeddings = embed_batch(embed_texts)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {exc}")

    # Create SQLite Template records first to get template_ids
    template_ids: list[int] = []
    async with async_session() as session:
        for chunk in all_chunks:
            template = Template(
                milvus_id=None,
                title=chunk.title,
                objective=chunk.objective,
                variables=json.dumps(chunk.variables),
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
