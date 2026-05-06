"""Add-on template SQLAlchemy model."""

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, func

from app.db.sqlite import Base


class AddonTemplate(Base):
    """SQLAlchemy model for add-on templates ingested via /add-addon."""

    __tablename__ = "addon_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    milvus_id = Column(BigInteger, nullable=True, unique=True)
    title = Column(String(256), nullable=False)
    objective = Column(String(1024), nullable=True)
    variables = Column(String(1024), nullable=True)  # JSON-serialized list
    full_text = Column(String, nullable=False)
    content_hash = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    def __repr__(self) -> str:
        return f"<AddonTemplate id={self.id} title='{self.title}' milvus_id={self.milvus_id}>"
