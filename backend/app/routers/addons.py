"""Add-on endpoints for registration, recommendation, and ingestion."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Callable, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.responses import JSONResponse

from app.db.milvus import ADDON_COLLECTION_NAME, search as milvus_search
from app.db.sqlite import async_session
from app.models.addon_templates import AddonTemplate
from app.schemas import IngestRequest, IngestTextRequest, JobEnqueueResponse
from app.services.chunker import chunk_file_auto, chunk_text_auto
from app.services.embedder import embed
from app.services.ingest_job import INGEST_KIND_ADDON, run_ingest_job
from app.services.ingest_validator import IngestValidationError, validate_parents
from app.services.job_runner import ProgressEmitter
from app.services.path_resolver import PathResolutionError, get_path_resolver
import app.services.job_runner as job_runner

logger = logging.getLogger(__name__)

router = APIRouter(tags=["addons"])

_custom_addons: List[dict] = []
_active_tasks: set[asyncio.Task] = set()


class AddonCreateRequest(BaseModel):
    name: str
    mode: str
    suffix: str
    description: str


class AddonResponse(BaseModel):
    id: int
    name: str
    mode: str
    suffix: str
    description: str
    source: str = "custom"


def _collect_file_paths(
    paths: list[str],
    directory: str | None,
    resolve: Callable,
) -> tuple[list[Path], str | None]:
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

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for fp in file_paths:
        resolved = fp.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_paths.append(fp)

    return unique_paths, resolved_directory


@router.get("/addons", response_model=List[AddonResponse])
async def list_addons() -> List[AddonResponse]:
    return [AddonResponse(**a) for a in _custom_addons]


@router.post("/addons", response_model=AddonResponse, status_code=201)
async def create_addon(request: AddonCreateRequest) -> AddonResponse:
    valid_modes = {"speed", "quality", "cost"}
    if request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"mode must be one of: {', '.join(sorted(valid_modes))}")
    addon = {
        "id": len(_custom_addons) + 1,
        "name": request.name,
        "mode": request.mode,
        "suffix": request.suffix,
        "description": request.description,
        "source": "custom",
    }
    _custom_addons.append(addon)
    logger.info("Registered custom add-on [%s] %s", request.mode, request.name)
    return AddonResponse(**addon)


@router.post("/addons/ingest", response_model=JobEnqueueResponse, status_code=202)
async def ingest_addon_documents(
    request: IngestRequest,
    resolve: Callable = Depends(get_path_resolver),
) -> JSONResponse:
    if not request.paths and not request.directory:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'paths' or 'directory' must be provided",
        )

    file_paths, resolved_directory = _collect_file_paths(request.paths, request.directory, resolve)

    all_chunks = []
    pre_validate_paths: list[Path] = list(file_paths)
    if resolved_directory is not None:
        dir_path = Path(resolved_directory)
        pre_validate_paths.extend(sorted(dir_path.glob("*.md")))
        pre_validate_paths.extend(sorted(dir_path.glob("*.pdf")))

    deduped_pre_validate_paths: list[Path] = []
    seen_prevalidate: set[Path] = set()
    for path in pre_validate_paths:
        resolved = path.resolve()
        if resolved not in seen_prevalidate:
            seen_prevalidate.add(resolved)
            deduped_pre_validate_paths.append(path)

    for fp in deduped_pre_validate_paths:
        try:
            chunks = await asyncio.to_thread(chunk_file_auto, str(fp))
            all_chunks.extend(chunks)
        except Exception:
            pass

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

    job_id = await job_runner.create_job(
        "addon_ingest",
        {"paths": [str(p) for p in file_paths], "directory": resolved_directory},
    )
    emit = ProgressEmitter(job_id=job_id)
    task = asyncio.create_task(
        run_ingest_job(
            job_id=job_id,
            paths=[str(p) for p in file_paths],
            directory=resolved_directory,
            emit=emit,
            ingest_kind=INGEST_KIND_ADDON,
        )
    )
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)

    logger.info("Enqueued addon ingest job %s (%d file paths)", job_id, len(file_paths))
    return JSONResponse(
        status_code=202,
        content=JobEnqueueResponse(
            job_id=job_id,
            status="pending",
            status_url=f"/api/v1/jobs/{job_id}",
        ).model_dump(),
    )


@router.post("/addons/ingest/text", response_model=JobEnqueueResponse, status_code=202)
async def ingest_addon_text(request: IngestTextRequest) -> JSONResponse:
    chunks = await asyncio.to_thread(chunk_text_auto, request.text)
    try:
        if chunks:
            validate_parents(chunks)
    except IngestValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": exc.error.code,
                "message": exc.error.message,
                "detail": exc.error.detail,
            },
        )

    job_id = await job_runner.create_job("addon_ingest", {"inline_text_count": 1})
    emit = ProgressEmitter(job_id=job_id)
    task = asyncio.create_task(
        run_ingest_job(
            job_id=job_id,
            paths=[],
            directory=None,
            emit=emit,
            ingest_kind=INGEST_KIND_ADDON,
            inline_texts=[request.text],
        )
    )
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)

    logger.info("Enqueued addon ingest text job %s", job_id)
    return JSONResponse(
        status_code=202,
        content=JobEnqueueResponse(
            job_id=job_id,
            status="pending",
            status_url=f"/api/v1/jobs/{job_id}",
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Recommendation models
# ---------------------------------------------------------------------------

class AddonRecommendRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(3, ge=1, le=50)
    tradeoff_preference: str = Field(
        "balanced",
        pattern="^(speed|cost|quality|balanced)$",
    )


class AddonRecommendResult(BaseModel):
    name: str
    mode: str
    suffix: str
    description: str
    score: float


class AddonRecommendResponse(BaseModel):
    results: list[AddonRecommendResult]


# ---------------------------------------------------------------------------
# Keyword maps for scoring
# ---------------------------------------------------------------------------

_SPEED_KEYWORDS: set[str] = {
    "speed", "fast", "quick", "brief", "terse", "verbose", "verbosity",
    "snappy", "rapid",
}
_COST_KEYWORDS: set[str] = {
    "cost", "cheap", "token", "tokens", "minimal", "efficient", "waste",
    "economy", "avoiding", "concise",
}
_QUALITY_KEYWORDS: set[str] = {
    "quality", "thorough", "detailed", "reasoning", "accurate", "complete",
    "comprehensive", "maintaining", "maintain",
    "global", "precision", "rigorous", "careful", "exact", "deep", "exhaustive",
    "meticulous", "robust", "best", "highest",
}
_MODE_KEYWORDS: dict[str, set[str]] = {
    "speed": _SPEED_KEYWORDS | _COST_KEYWORDS,
    "cost": _COST_KEYWORDS,
    "quality": _QUALITY_KEYWORDS,
}


_TRADEOFF_MODE_BONUS: dict[str, float] = {
    "quality": 2.0,
    "speed": 2.0,
    "cost": 2.0,
    "balanced": 0.5,
}


def _query_word_set(query: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", query.lower()))


def _score_addon(
    mode: str,
    description: str,
    query_words: set[str],
    tradeoff: str,
) -> float:
    mode_matches = len(query_words & _MODE_KEYWORDS.get(mode, set()))
    desc_words = set(re.findall(r"[a-z0-9]+", description.lower()))
    desc_matches = len(query_words & desc_words)
    score = mode_matches * 2.0 + desc_matches * 0.5
    if tradeoff != "balanced" and mode == tradeoff:
        score += _TRADEOFF_MODE_BONUS.get(tradeoff, 0.0)
    return score


def _vector_hits_to_addon_ids(raw_hits: list[dict], top_k: int) -> list[tuple[int, float]]:
    """Collapse chunk-level Milvus hits to best score per add-on template id."""
    best_by_tid: dict[int, float] = {}
    for hit in raw_hits:
        tid_raw = hit.get("template_id")
        if tid_raw is None:
            continue
        try:
            tid = int(tid_raw)
        except (TypeError, ValueError):
            continue
        if tid <= 0:
            continue
        sc = float(hit.get("score", 0.0))
        prev = best_by_tid.get(tid)
        if prev is None or sc > prev:
            best_by_tid[tid] = sc
    ordered = sorted(best_by_tid.items(), key=lambda pair: pair[1], reverse=True)
    return ordered[:top_k]


async def _addon_results_from_vector_hits(
    ordered_ids_scores: list[tuple[int, float]],
) -> list[AddonRecommendResult]:
    """Load SQLite rows for Milvus parent ids and build API results."""
    if not ordered_ids_scores:
        return []
    ids = [tid for tid, _ in ordered_ids_scores]
    score_by_id = {tid: sc for tid, sc in ordered_ids_scores}
    async with async_session() as session:
        result = await session.execute(select(AddonTemplate).where(AddonTemplate.id.in_(ids)))
        rows = list(result.scalars().all())
    by_id = {row.id: row for row in rows}
    out: list[AddonRecommendResult] = []
    for tid, sc in ordered_ids_scores:
        row = by_id.get(tid)
        if row is None:
            continue
        desc = (row.objective or "").strip() or (row.title or "Ingested add-on")
        out.append(
            AddonRecommendResult(
                name=row.title,
                mode="custom",
                suffix=row.full_text,
                description=desc,
                score=score_by_id.get(tid, sc),
            )
        )
    return out


def _memory_custom_addon_candidates(query_words: set[str], tradeoff: str) -> list[AddonRecommendResult]:
    """Rank API-registered in-memory add-ons (no vector index)."""
    candidates: list[AddonRecommendResult] = []
    for addon in _custom_addons:
        score = _score_addon(addon["mode"], addon["description"], query_words, tradeoff)
        candidates.append(
            AddonRecommendResult(
                name=addon["name"],
                mode=addon["mode"],
                suffix=addon["suffix"],
                description=addon["description"],
                score=score,
            )
        )
    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Recommend endpoint
# ---------------------------------------------------------------------------

@router.post("/addons/recommend", response_model=AddonRecommendResponse)
async def recommend_addons(request: AddonRecommendRequest) -> AddonRecommendResponse:
    """Rank add-ons like prompt search: vector retrieval over ingested add-ons, top_k capped.

    Ingested templates use the same Milvus + embed flow as ``/recommend``. The legacy
    speed/cost/quality built-ins are not listed here; they remain attachable via each
    prompt's ``applicable_addons`` from ``/recommend`` when a tradeoff is selected.
    """
    query = request.query.strip()
    query_words = _query_word_set(query)
    tradeoff = request.tradeoff_preference

    try:
        query_vector = embed(query)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Query embedding failed: {exc}",
        ) from exc

    raw_hits: list[dict] = []
    try:
        raw_hits = milvus_search(
            query_vector,
            top_k=max(request.top_k * 4, request.top_k),
            collection_name=ADDON_COLLECTION_NAME,
        )
    except Exception as exc:
        logger.warning("Add-on Milvus search failed, using memory add-ons only: %s", exc)

    ordered = _vector_hits_to_addon_ids(raw_hits, request.top_k)
    vector_results = await _addon_results_from_vector_hits(ordered)
    if vector_results:
        return AddonRecommendResponse(results=vector_results[: request.top_k])

    memory_ranked = _memory_custom_addon_candidates(query_words, tradeoff)
    return AddonRecommendResponse(results=memory_ranked[: request.top_k])
