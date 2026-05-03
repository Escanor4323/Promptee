"""Model SQLAlchemy model.

Represents available AI models (Claude variants, custom models, etc.)
that can be used for prompt execution and tracked for preference analysis.
"""

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from app.db.sqlite import Base


class Model(Base):
    """SQLAlchemy model for the ``models`` table."""

    __tablename__ = "models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)  # "claude-opus-4-7", "gpt-4", etc.
    type = Column(String(64), nullable=False)  # "claude" | "gpt" | "custom"
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Model id={self.id} name={self.name} type={self.type}>"
