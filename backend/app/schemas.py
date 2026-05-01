"""Pydantic request/response schemas for Promptee API endpoints."""

from pydantic import BaseModel, Field


# --- AddOn schemas ---


class AddOnSchema(BaseModel):
    name: str
    mode: str
    suffix: str
    description: str


# --- Ingest schemas ---


class IngestRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    directory: str | None = None


class IngestResponse(BaseModel):
    ingested: int
    titles: list[str]


# --- Recommend schemas ---


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=50)
    tradeoff_preference: str = Field("balanced", pattern="^(speed|cost|quality|balanced)$")


class RecommendItem(BaseModel):
    id: int
    template_id: int
    title: str
    objective: str
    full_text: str
    variables: list[str]
    hybrid_score: float
    applicable_addons: list[AddOnSchema]


class RecommendResponse(BaseModel):
    results: list[RecommendItem]


# --- Bulk search result (used internally by recommend) ---


class BulkSearchResult(BaseModel):
    id: int
    template_id: int
    title: str
    objective: str
    full_text: str
    variables: list[str]
    score: float
