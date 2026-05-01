"""Promptee Database Models

ERD:
    Templates (1) ───< (N) Executions (1) ───< (N) Feedback
    Templates.milvus_id ──> Milvus vector ID (cross-database reference)

Tradeoff Mapping:
    SPEED   = f(low latency, low total tokens) -> tradeoff_speed (0-1)
    COST    = f(low total tokens) -> tradeoff_cost (0-1)
    QUALITY = f(avg feedback score) -> tradeoff_quality (0-1)
"""

from backend.app.models.executions import Execution
from backend.app.models.feedback import Feedback
from backend.app.models.templates import Template

__all__ = ["Execution", "Feedback", "Template"]
