"""POST/GET /api/v1/addons endpoints for custom prompt add-ons."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.addon import BUILTIN_ADDONS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["addons"])

_custom_addons: List[dict] = []


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


# ---------------------------------------------------------------------------
# Recommendation models
# ---------------------------------------------------------------------------

class AddonRecommendRequest(BaseModel):
    query: str
    top_k: int = 3


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
}
_MODE_KEYWORDS: dict[str, set[str]] = {
    "speed": _SPEED_KEYWORDS | _COST_KEYWORDS,
    "cost": _COST_KEYWORDS,
    "quality": _QUALITY_KEYWORDS,
}


def _score_addon(mode: str, description: str, query_words: set[str]) -> float:
    mode_matches = len(query_words & _MODE_KEYWORDS.get(mode, set()))
    desc_words = set(description.lower().split())
    desc_matches = len(query_words & desc_words)
    return mode_matches * 2.0 + desc_matches * 0.5


# ---------------------------------------------------------------------------
# Recommend endpoint
# ---------------------------------------------------------------------------

@router.post("/addons/recommend", response_model=AddonRecommendResponse)
async def recommend_addons(request: AddonRecommendRequest) -> AddonRecommendResponse:
    query_words = set(request.query.lower().split())

    candidates: list[AddonRecommendResult] = []

    for addon in BUILTIN_ADDONS.values():
        score = _score_addon(addon.mode, addon.description, query_words)
        candidates.append(
            AddonRecommendResult(
                name=addon.name,
                mode=addon.mode,
                suffix=addon.suffix,
                description=addon.description,
                score=score,
            )
        )

    for addon in _custom_addons:
        score = _score_addon(addon["mode"], addon["description"], query_words)
        candidates.append(
            AddonRecommendResult(
                name=addon["name"],
                mode=addon["mode"],
                suffix=addon["suffix"],
                description=addon["description"],
                score=score,
            )
        )

    if all(c.score == 0.0 for c in candidates):
        # Fallback: return all built-ins with score 0
        fallback = [
            AddonRecommendResult(
                name=a.name,
                mode=a.mode,
                suffix=a.suffix,
                description=a.description,
                score=0.0,
            )
            for a in BUILTIN_ADDONS.values()
        ]
        return AddonRecommendResponse(results=fallback)

    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    return AddonRecommendResponse(results=ranked[: request.top_k])
