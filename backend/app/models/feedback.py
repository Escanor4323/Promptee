"""Feedback SQLAlchemy model.

Captures human-in-the-loop quality ratings (1-5) and optional notes
for each execution. Provides the ground-truth signal used to compute
the ``tradeoff_quality`` score.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from backend.app.db.sqlite import Base


class Feedback(Base):
    """SQLAlchemy model for the ``feedback`` table."""

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "quality_score >= 1 AND quality_score <= 5",
            name="ck_feedback_quality_score_range",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(
        Integer, ForeignKey("executions.id"), nullable=False
    )
    quality_score = Column(Integer, nullable=False)  # 1 to 5
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    execution = relationship("Execution", back_populates="feedback", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Feedback id={self.id} execution_id={self.execution_id} "
            f"quality_score={self.quality_score}>"
        )
