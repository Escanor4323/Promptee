"""BM25 keyword scoring for hybrid dense + sparse retrieval.

Used as a post-retrieval reranker: after Milvus returns top-K dense candidates,
BM25 scores are computed client-side against the full parent text to produce
a hybrid score that balances semantic similarity with keyword precision.
"""

import re

from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    """Lowercase and split on non-alphanumeric characters."""
    return re.findall(r"\b\w+\b", text.lower())


def compute_bm25_scores(query: str, documents: list[str]) -> list[float]:
    """Return BM25 scores for query against each document, normalized to [0, 1].

    Args:
        query: The search query string.
        documents: List of document texts to score against.

    Returns:
        List of BM25 scores (same length as documents), normalized to [0, 1].
        Returns an empty list when documents is empty.
    """
    if not documents:
        return []

    tokenized_docs = [tokenize(doc) for doc in documents]
    # BM25Okapi raises ZeroDivisionError when every tokenized doc is empty
    # (e.g. all docs are empty strings / sentinel template_id=0 lookups).
    if all(len(tokens) == 0 for tokens in tokenized_docs):
        return [0.0] * len(documents)

    tokenized_query = tokenize(query)
    bm25 = BM25Okapi(tokenized_docs)
    scores = bm25.get_scores(tokenized_query)

    max_score = scores.max() if scores.max() > 0 else 1.0
    return (scores / max_score).tolist()
