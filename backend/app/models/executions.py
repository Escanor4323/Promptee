"""Execution SQLAlchemy model.

Records telemetry data for each prompt execution, including latency,
token usage, context window utilization, verbosity, and computed
tradeoff scores (speed, cost, quality).
"""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from backend.app.db.sqlite import Base


class Execution(Base):
    """SQLAlchemy model for the ``executions`` table."""

    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(
        Integer, ForeignKey("templates.id"), nullable=False
    )
    latency_ms = Column(Float, nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    context_window_pct = Column(Float, nullable=False)
    verbosity = Column(String(32), nullable=False)  # "terse"|"moderate"|"verbose"
    tradeoff_speed = Column(Float, default=0.0, nullable=False)
    tradeoff_cost = Column(Float, default=0.0, nullable=False)
    tradeoff_quality = Column(Float, default=0.0, nullable=False)
    addon_mode = Column(String(64), nullable=True)  # "speed"|"quality"|"cost"|"balanced"
    model_id = Column(String(128), nullable=True)  # "claude-opus-4-7"|"claude-sonnet-4-6"|etc
    executed_at = Column(DateTime, server_default=func.now(), nullable=False)

    template = relationship("Template", back_populates="executions", lazy="selectin")
    feedback = relationship("Feedback", back_populates="execution", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Execution id={self.id} template_id={self.template_id} "
            f"latency_ms={self.latency_ms}>"
        )
