"""ModelPreference SQLAlchemy model.

Tracks model performance across template-addon combinations.
Aggregates execution counts and quality scores by model.
"""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from backend.app.db.sqlite import Base


class ModelPreference(Base):
    """SQLAlchemy model for the ``model_preferences`` table."""

    __tablename__ = "model_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    model_id = Column(String(128), nullable=False)  # "claude-opus-4-7", etc.
    addon_mode = Column(String(64), nullable=True)  # "speed" | "quality" | "cost" | "balanced" | None
    avg_quality_score = Column(Float, default=0.0, nullable=False)
    execution_count = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    template = relationship("Template", back_populates="preferences", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("template_id", "model_id", "addon_mode", name="uq_template_model_addon"),
    )

    def __repr__(self) -> str:
        return (
            f"<ModelPreference id={self.id} template_id={self.template_id} "
            f"model_id={self.model_id} addon_mode={self.addon_mode}>"
        )
