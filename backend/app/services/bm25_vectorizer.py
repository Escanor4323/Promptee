"""BM25 sparse vector encoder for Milvus SPARSE_FLOAT_VECTOR fields.

Converts raw text into a sparse dict {term_hash: bm25_weight} suitable for
insertion into and searching against a Milvus SPARSE_FLOAT_VECTOR column.

Why hash-based vocabulary?
  Milvus SPARSE_FLOAT_VECTOR uses integer keys. We hash each unique term with a
  24-bit FNV-1a hash so the vocabulary requires no pre-fitting step while
  keeping the collision probability below 0.01 % for typical prompt corpora.

Usage (ingest)::

    from app.services.bm25_vectorizer import bm25_sparse_vectors
    sparse_vecs = bm25_sparse_vectors(child_texts)   # list of dicts

Usage (query)::

    from app.services.bm25_vectorizer import bm25_query_vector
    sparse_query = bm25_query_vector(query_text, corpus=child_texts)
"""

import re
from typing import Sequence

import numpy as np
from rank_bm25 import BM25Okapi

_HASH_MASK = (1 << 24) - 1


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _fnv1a_24(term: str) -> int:
    """FNV-1a 32-bit hash truncated to 24 bits."""
    h = 2166136261
    for ch in term.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return h & _HASH_MASK


def _to_sparse_dict(terms: list[str], scores: np.ndarray, max_score: float) -> dict[int, float]:
    if max_score <= 0:
        return {}
    result: dict[int, float] = {}
    for term, score in zip(terms, scores):
        if score > 0:
            result[_fnv1a_24(term)] = float(score / max_score)
    return result


def bm25_sparse_vectors(texts: Sequence[str]) -> list[dict[int, float]]:
    """Fit BM25 over *texts* and return one sparse {hash: weight} dict per document.

    The returned dicts are ready for Milvus SPARSE_FLOAT_VECTOR insertion.
    Empty documents produce an empty dict {}; callers should substitute the
    Milvus sentinel {0: 0.0} before inserting.

    Args:
        texts: Corpus of child chunk texts to encode.

    Returns:
        List of sparse dicts, one per input text.
    """
    tokenized = [_tokenize(t) for t in texts]

    # BM25Okapi raises ZeroDivisionError when every doc tokenizes to nothing.
    if all(len(t) == 0 for t in tokenized):
        return [{} for _ in texts]

    bm25 = BM25Okapi(tokenized)

    result: list[dict[int, float]] = []
    for doc_tokens in tokenized:
        if not doc_tokens:
            result.append({})
            continue
        scores = bm25.get_scores(doc_tokens)
        max_score = float(scores.max()) if scores.max() > 0 else 0.0
        result.append(_to_sparse_dict(doc_tokens, scores, max_score))

    return result


def bm25_query_vector(query: str, corpus: Sequence[str]) -> dict[int, float]:
    """Fit BM25 over *corpus* and return a sparse query vector for *query*.

    Args:
        query:  The user query string.
        corpus: Corpus texts used to fit the BM25 model (e.g. child_texts from ingest).

    Returns:
        Sparse dict {term_hash: weight} for the query, or {} when no scores.
    """
    if not corpus:
        return {}

    tokenized_corpus = [_tokenize(t) for t in corpus]
    non_empty = [t for t in tokenized_corpus if t]
    if not non_empty:
        return {}

    bm25 = BM25Okapi(non_empty)
    query_tokens = _tokenize(query)
    if not query_tokens:
        return {}

    scores = bm25.get_scores(query_tokens)
    max_score = float(scores.max()) if scores.max() > 0 else 0.0
    return _to_sparse_dict(query_tokens, scores, max_score)
