"""Template SQLAlchemy model.

Represents a prompt template registered in the local SQLite database.
Each template maps to a Milvus vector via ``milvus_id`` for cross-database
reference between the relational store and the vector store.
"""

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from backend.app.db.sqlite import Base


class Template(Base):
    """SQLAlchemy model for the ``templates`` table."""

    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    milvus_id = Column(Integer, nullable=True, unique=True)
    title = Column(String(256), nullable=False)
    objective = Column(String(1024), nullable=True)
    variables = Column(String(1024), nullable=True)  # JSON-serialized list
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    executions = relationship("Execution", back_populates="template", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Template id={self.id} title='{self.title}' milvus_id={self.milvus_id}>"
