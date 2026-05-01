"""Dual-vector embedding logic using sentence-transformers.

Embeds ONLY the title + objective strings into the vector space,
NOT the full prompt text. Uses all-MiniLM-L6-v2 (dim=384).
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_model: Optional[object] = None


def get_model():
    """Lazy-load the sentence-transformer model (singleton)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        from backend.app.config import get_settings
        settings = get_settings()
        logger.info("Loading embedding model: %s", settings.embedding_model_name)
        _model = SentenceTransformer(settings.embedding_model_name)
    return _model


def embed(text: str) -> np.ndarray:
    """Embed a single text string. Returns shape (384,)."""
    model = get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.astype(np.float32)


def embed_batch(texts: list[str]) -> np.ndarray:
    """Embed multiple text strings. Returns shape (N, 384)."""
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.astype(np.float32)


def embed_chunk_summary(title: str, objective: str) -> np.ndarray:
    """Embed title + objective concatenated (the dual-vector strategy).

    The full prompt text is NOT embedded — only the summary fields
    that capture the template's intent.
    """
    summary = f"{title} {objective}".strip()
    if not summary:
        summary = title or "untitled"
    return embed(summary)
