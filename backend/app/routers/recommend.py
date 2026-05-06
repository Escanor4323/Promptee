"""POST /api/v1/recommend endpoint with Milvus hybrid search and reranking.

Flow:
  1. Embed query -> dense vector (sentence-transformers) + sparse vector (BM25).
  2. Milvus hybrid_search fuses both streams via WeightedRanker (70 % dense, 30 % sparse).
  3. Rerank top hits using historical telemetry (quality + popularity boosts).
  4. Fetch full_text from SQLite, attach applicable PromptAddOns.

BM25 is now executed fully on the Milvus side (SPARSE_FLOAT_VECTOR field +
SPARSE_INVERTED_INDEX). Client-side BM25 post-processing has been removed.
"""

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.milvus import hybrid_search as milvus_search
from app.db.sqlite import async_session
from app.models.templates import Template
from app.schemas import (
    AddOnSchema,
    RecommendItem,
    RecommendRequest,
    RecommendResponse,
)
from app.services.addon import get_addons_for_preference
from app.services.bm25_vectorizer import bm25_query_vector
from app.services.embedder import embed
from app.services.reranker import rerank

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend_prompts(request: RecommendRequest) -> RecommendResponse:
    """Search for semantically similar prompt templates with Milvus hybrid search.

    1. Embed query (dense + BM25 sparse) -> Milvus hybrid_search
    2. Rerank using historical telemetry (quality + popularity boosts)
    3. Attach applicable PromptAddOns for the tradeoff preference
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query string must not be empty")

    query = request.query.strip()

    try:
        query_dense = embed(query)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Query embedding failed: {exc}")

    # Build the BM25 sparse query vector from the query text alone.
    # We use the query as a single-element corpus so the vectorizer produces
    # hash-keyed weights for all query terms.
    query_sparse = bm25_query_vector(query, corpus=[query])

    try:
        raw_results = milvus_search(query_dense, query_sparse, top_k=request.top_k)
    except Exception as exc:
        logger.error("Milvus hybrid search failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vector search failed: {exc}")

    if not raw_results:
        return RecommendResponse(results=[])

    try:
        async with async_session() as session:
            reranked = await rerank(
                results=raw_results,
                tradeoff_preference=request.tradeoff_preference,
                session=session,
                top_k=5,
            )
    except Exception as exc:
        logger.warning("Reranking failed, falling back to semantic order: %s", exc)
        reranked = raw_results[:5]
        for r in reranked:
            r["hybrid_score"] = r.get("score", 0.0)

    addons = get_addons_for_preference(request.tradeoff_preference)
    addon_schemas = [
        AddOnSchema(name=a.name, mode=a.mode, suffix=a.suffix, description=a.description)
        for a in addons
    ]

    # Fetch full_text for each reranked result from SQLite
    enriched: list[tuple[dict, str]] = []
    async with async_session() as session:
        for r in reranked:
            template_id = r.get("template_id", 0)
            full_text = ""
            if template_id:
                result = await session.execute(
                    select(Template.full_text).where(Template.id == template_id)
                )
                full_text = result.scalar_one_or_none() or ""
            enriched.append((r, full_text))

    items: list[RecommendItem] = [
        RecommendItem(
            id=r["id"],
            template_id=r.get("template_id", 0),
            title=r["title"],
            objective=r.get("objective", ""),
            full_text=full_text,
            variables=r.get("variables", []),
            hybrid_score=r.get("hybrid_score", 0.0),
            applicable_addons=addon_schemas,
        )
        for r, full_text in enriched
    ]

    logger.info(
        "Returning %d recommendations for query: %s (preference=%s)",
        len(items), query[:80], request.tradeoff_preference,
    )

    return RecommendResponse(results=items)
