"""POST /api/v1/recommend endpoint with hybrid reranking and AddOns.

Embeds the query, searches Milvus for top-N semantic results, then
reranks them using historical telemetry data from SQLite and applies
PromptAddOn injection based on the user's tradeoff preference.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.app.db.milvus import search as milvus_search
from backend.app.db.sqlite import async_session
from backend.app.schemas import (
    AddOnSchema,
    RecommendItem,
    RecommendRequest,
    RecommendResponse,
)
from backend.app.services.addon import get_addons_for_preference
from backend.app.services.embedder import embed
from backend.app.services.reranker import rerank

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend_prompts(request: RecommendRequest) -> RecommendResponse:
    """Search for semantically similar prompt templates with hybrid reranking.

    1. Embed query -> Milvus semantic search (top_k results)
    2. Rerank using historical telemetry (quality + popularity boosts)
    3. Attach applicable PromptAddOns for the tradeoff preference
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query string must not be empty")

    try:
        query_vector = embed(request.query.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Query embedding failed: {exc}")

    try:
        raw_results = milvus_search(query_vector, top_k=request.top_k)
    except Exception as exc:
        logger.error("Milvus search failed: %s", exc, exc_info=True)
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

    items: list[RecommendItem] = []
    for r in reranked:
        items.append(RecommendItem(
            id=r["id"],
            template_id=r.get("template_id", 0),
            title=r["title"],
            objective=r.get("objective", ""),
            full_text=r["full_text"],
            variables=r.get("variables", []),
            hybrid_score=r.get("hybrid_score", 0.0),
            applicable_addons=addon_schemas,
        ))

    logger.info(
        "Returning %d recommendations for query: %s (preference=%s)",
        len(items), request.query[:80], request.tradeoff_preference,
    )

    return RecommendResponse(results=items)
