"""GET /api/v1/templates — list all ingested prompt templates.

Supports sorting by any scalar column via ?sort_by=<field>&order=asc|desc.
Full text is omitted from the list response to keep payloads small; use the
recommend endpoint when the full prompt body is needed.
"""

import json
import logging
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import asc, desc, select

from app.db.sqlite import async_session
from app.models.templates import Template
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])

# Columns the caller is allowed to sort by.  Mapping keeps SQL injection risk zero.
_SORT_COLUMNS = {
    "id": Template.id,
    "title": Template.title,
    "objective": Template.objective,
    "created_at": Template.created_at,
    "updated_at": Template.updated_at,
}

VALID_SORT_FIELDS = sorted(_SORT_COLUMNS.keys())


class TemplateItem(BaseModel):
    """Lightweight template summary returned by GET /api/v1/templates."""

    id: int
    title: str
    objective: str
    variables: list[str]
    created_at: str
    updated_at: str | None


@router.get("/templates", response_model=list[TemplateItem])
async def list_templates(
    sort_by: str = Query("title", description=f"Sort field. One of: {', '.join(VALID_SORT_FIELDS)}"),
    order: Literal["asc", "desc"] = Query("asc", description="Sort direction: asc or desc"),
) -> list[TemplateItem]:
    """Return all ingested prompt templates.

    Query parameters:
    - **sort_by**: field to sort by (id, title, objective, created_at, updated_at)
    - **order**: sort direction (asc, desc)

    Unknown sort_by values silently fall back to ``title``.
    """
    sort_col = _SORT_COLUMNS.get(sort_by, Template.title)
    direction = desc if order == "desc" else asc

    async with async_session() as session:
        result = await session.execute(
            select(Template).order_by(direction(sort_col))
        )
        templates = result.scalars().all()

    items = []
    for t in templates:
        try:
            variables = json.loads(t.variables) if t.variables else []
        except (json.JSONDecodeError, TypeError):
            variables = []
        items.append(
            TemplateItem(
                id=t.id,
                title=t.title,
                objective=t.objective or "",
                variables=variables,
                created_at=str(t.created_at),
                updated_at=str(t.updated_at) if t.updated_at else None,
            )
        )

    logger.info("list_templates sort_by=%s order=%s count=%d", sort_by, order, len(items))
    return items
