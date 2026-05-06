"""Unit tests for app.services.bm25_vectorizer.

Verifies that bm25_sparse_vectors and bm25_query_vector produce valid
Milvus SPARSE_FLOAT_VECTOR dicts (int keys, float values in [0, 1]).
"""

import pytest

from app.services.bm25_vectorizer import bm25_query_vector, bm25_sparse_vectors


def test_sparse_vectors_returns_one_dict_per_text():
    texts = ["write python code", "review security policy", "generate unit tests"]
    result = bm25_sparse_vectors(texts)
    assert len(result) == len(texts)


def test_sparse_vectors_keys_are_ints_values_in_unit_range():
    texts = ["optimize database queries for PostgreSQL", "secure REST API design"]
    result = bm25_sparse_vectors(texts)
    for sparse in result:
        for k, v in sparse.items():
            assert isinstance(k, int), f"key {k!r} is not int"
            assert 0.0 <= v <= 1.0, f"weight {v} out of [0,1]"


def test_sparse_vectors_empty_text_produces_empty_dict():
    result = bm25_sparse_vectors([""])
    assert result[0] == {}


def test_sparse_vectors_single_text():
    result = bm25_sparse_vectors(["hello world"])
    assert len(result) == 1
    # May be empty if all tokens score 0 against a single-doc corpus; that's OK.
    for k, v in result[0].items():
        assert isinstance(k, int)
        assert v >= 0.0


def test_query_vector_keys_are_ints_values_in_unit_range():
    corpus = [
        "write a Python function to parse JSON",
        "design a secure authentication flow",
        "optimize slow SQL queries",
    ]
    sparse = bm25_query_vector("parse JSON securely", corpus=corpus)
    for k, v in sparse.items():
        assert isinstance(k, int)
        assert 0.0 <= v <= 1.0


def test_query_vector_empty_corpus_returns_empty():
    sparse = bm25_query_vector("anything", corpus=[])
    assert sparse == {}


def test_query_vector_empty_query_returns_empty():
    sparse = bm25_query_vector("", corpus=["some document"])
    assert sparse == {}


def test_hybrid_search_receives_correct_types(monkeypatch):
    """Smoke test: bm25_query_vector result is suitable for hybrid_search."""
    query = "write unit tests for async code"
    corpus = ["async python testing with pytest", "fastapi test client patterns"]
    sparse = bm25_query_vector(query, corpus=corpus)
    # Milvus expects a plain dict with int keys and float values.
    assert isinstance(sparse, dict)
    for k, v in sparse.items():
        assert isinstance(k, int)
        assert isinstance(v, float)
