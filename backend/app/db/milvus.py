"""Milvus vector database client and collection schema.

Collection: prompt_templates (and addon_templates)

When the running Milvus server supports SPARSE_FLOAT_VECTOR (≥ 2.4):
  Fields: id, template_id, vector(384), sparse_vector, title, objective, variables
  Indexes: IVF_FLAT/COSINE on vector, SPARSE_INVERTED_INDEX/IP on sparse_vector
  Search: hybrid AnnSearchRequest fused by WeightedRanker (70 % dense, 30 % sparse)

When the server does not support sparse (< 2.4 or existing schema lacks sparse_vector):
  Fields: id, template_id, vector(384), title, objective, variables
  Search: dense-only COSINE ANN search

Sparse capability is detected once per collection and cached in ``_sparse_enabled``.
"""

import json
import logging

from pymilvus import (
    AnnSearchRequest,
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusException,
    RRFRanker,  # noqa: F401 — available for future use
    WeightedRanker,
    connections,
    utility,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

_collections: dict[str, Collection] = {}

# Per-collection sparse capability flag.  Set in get_or_create_collection.
_sparse_enabled: dict[str, bool] = {}

COLLECTION_NAME = "prompt_templates"
ADDON_COLLECTION_NAME = "addon_templates"
VECTOR_DIM = 384

HYBRID_DENSE_WEIGHT = 0.70
HYBRID_SPARSE_WEIGHT = 0.30

_EMPTY_SPARSE: dict[int, float] = {0: 0.0}


def _get_connection_alias() -> str:
    return "default"


def connect() -> None:
    """Connect to Milvus server."""
    settings = get_settings()
    connections.connect(
        alias=_get_connection_alias(),
        host=settings.milvus_host,
        port=str(settings.milvus_port),
    )
    logger.info("Connected to Milvus at %s:%d", settings.milvus_host, settings.milvus_port)


def _build_sparse_schema() -> CollectionSchema:
    return CollectionSchema(
        fields=[
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="template_id", dtype=DataType.INT64),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM),
            FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="objective", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="variables", dtype=DataType.VARCHAR, max_length=1024),
        ],
        description="Prompt template vectors — dense + sparse (full_text in SQLite)",
    )


def _build_dense_schema() -> CollectionSchema:
    return CollectionSchema(
        fields=[
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="template_id", dtype=DataType.INT64),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="objective", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="variables", dtype=DataType.VARCHAR, max_length=1024),
        ],
        description="Prompt template vectors — dense-only (full_text in SQLite)",
    )


def _has_sparse_field(collection: Collection) -> bool:
    """Return True when the collection schema includes a sparse_vector field."""
    try:
        return any(f.name == "sparse_vector" for f in collection.schema.fields)
    except Exception:
        return False


def get_or_create_collection(collection_name: str = COLLECTION_NAME) -> Collection:
    """Get or create a Milvus collection, detecting sparse support automatically.

    For existing collections the schema is inspected to determine whether
    sparse_vector is present.  For new collections a sparse schema is attempted
    first; if the server rejects it (older Milvus < 2.4) a dense-only schema is
    used instead.  The result is stored in ``_sparse_enabled[collection_name]``.
    """
    if collection_name in _collections:
        return _collections[collection_name]

    connect()

    if utility.has_collection(collection_name):
        collection = Collection(collection_name)
        _collections[collection_name] = collection
        has_sparse = _has_sparse_field(collection)
        _sparse_enabled[collection_name] = has_sparse
        logger.info(
            "Loaded existing collection: %s (sparse=%s)", collection_name, has_sparse
        )
        return collection

    # New collection — try sparse first, fall back to dense-only.
    try:
        schema = _build_sparse_schema()
        collection = Collection(name=collection_name, schema=schema)
        collection.create_index(
            field_name="vector",
            index_params={
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            },
        )
        collection.create_index(
            field_name="sparse_vector",
            index_params={
                "metric_type": "IP",
                "index_type": "SPARSE_INVERTED_INDEX",
                "params": {"drop_ratio_build": 0.2},
            },
        )
        _sparse_enabled[collection_name] = True
        logger.info(
            "Created collection %s with dense+sparse indexes", collection_name
        )
    except MilvusException as exc:
        logger.warning(
            "Sparse schema failed for %s (%s). Using dense-only schema.",
            collection_name, exc,
        )
        # Drop the partially-created collection if it exists before retrying.
        try:
            if utility.has_collection(collection_name):
                utility.drop_collection(collection_name)
        except Exception:
            pass

        schema = _build_dense_schema()
        collection = Collection(name=collection_name, schema=schema)
        collection.create_index(
            field_name="vector",
            index_params={
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            },
        )
        _sparse_enabled[collection_name] = False
        logger.info("Created collection %s with dense-only index", collection_name)

    _collections[collection_name] = collection
    return collection


def sparse_enabled(collection_name: str = COLLECTION_NAME) -> bool:
    """Return True when the named collection has a sparse_vector field."""
    return _sparse_enabled.get(collection_name, False)


def insert_chunks(
    child_texts: list[str],
    embeddings: list,
    sparse_vectors: list[dict[int, float]],
    template_ids: list[int],
    chunk_indices: list[int],
    token_counts: list[int],
    parent_titles: list[str],
    collection_name: str = COLLECTION_NAME,
) -> list[int]:
    """Insert child chunk embeddings into Milvus.

    Includes sparse_vector only when the collection supports it.
    sparse_vectors is always accepted in the call signature so callers
    do not need to branch on capability — this function handles it internally.
    """
    collection = get_or_create_collection(collection_name)
    use_sparse = sparse_enabled(collection_name)

    n = len(child_texts)
    if len(embeddings) != n:
        raise ValueError(f"insert_chunks: len(embeddings)={len(embeddings)} != {n}")
    if len(sparse_vectors) != n:
        raise ValueError(f"insert_chunks: len(sparse_vectors)={len(sparse_vectors)} != {n}")
    if len(template_ids) != n:
        raise ValueError(f"insert_chunks: len(template_ids)={len(template_ids)} != {n}")
    if len(parent_titles) != n:
        raise ValueError(f"insert_chunks: len(parent_titles)={len(parent_titles)} != {n}")

    rows: list[dict] = []
    for embedding, sparse_vec, template_id, title in zip(
        embeddings, sparse_vectors, template_ids, parent_titles
    ):
        dense = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        row: dict = {
            "template_id": int(template_id),
            "vector": dense,
            "title": (title or "")[:256],
            "objective": "",
            "variables": "[]",
        }
        if use_sparse:
            row["sparse_vector"] = sparse_vec if sparse_vec else _EMPTY_SPARSE
        rows.append(row)

    result = collection.insert(rows)
    collection.flush()
    mode = "dense+sparse" if use_sparse else "dense-only"
    logger.info("Inserted %d child chunks into Milvus (%s)", len(rows), mode)
    return list(result.primary_keys)


def search(query_vector, top_k: int = 10, collection_name: str = COLLECTION_NAME) -> list[dict]:
    """Dense-only COSINE ANN search."""
    collection = get_or_create_collection(collection_name)

    try:
        if collection.num_entities == 0:
            logger.info("Milvus collection is empty. Returning 0 results.")
            return []
    except MilvusException as exc:
        logger.info("Milvus collection not ready / empty (%s). Returning 0 results.", exc)
        return []

    collection.load()

    results = collection.search(
        data=[query_vector.tolist() if hasattr(query_vector, "tolist") else list(query_vector)],
        anns_field="vector",
        param={"metric_type": "COSINE", "params": {"nprobe": 16}},
        limit=top_k,
        output_fields=["template_id", "title", "objective", "variables"],
    )

    hits: list[dict] = []
    for hit in results[0]:
        hits.append({
            "id": hit.id,
            "template_id": hit.entity.get("template_id"),
            "title": hit.entity.get("title"),
            "objective": hit.entity.get("objective"),
            "variables": json.loads(hit.entity.get("variables", "[]")),
            "score": hit.score,
        })

    return hits


def hybrid_search(
    query_dense,
    query_sparse: dict[int, float],
    top_k: int = 10,
    collection_name: str = COLLECTION_NAME,
    dense_weight: float = HYBRID_DENSE_WEIGHT,
    sparse_weight: float = HYBRID_SPARSE_WEIGHT,
) -> list[dict]:
    """Hybrid dense + sparse search (falls back to dense-only when unsupported).

    When the collection lacks a sparse_vector field, delegates to ``search()``.
    When ``collection.hybrid_search`` raises MilvusException, also falls back.
    """
    # If this collection does not have a sparse field, skip straight to dense.
    if not sparse_enabled(collection_name):
        logger.debug(
            "hybrid_search: sparse not enabled for %s, using dense-only.", collection_name
        )
        return search(query_dense, top_k=top_k, collection_name=collection_name)

    collection = get_or_create_collection(collection_name)

    try:
        if collection.num_entities == 0:
            logger.info("Milvus collection is empty. Returning 0 results.")
            return []
    except MilvusException as exc:
        logger.info("Milvus collection not ready / empty (%s). Returning 0 results.", exc)
        return []

    collection.load()

    candidate_limit = min(top_k * 4, 256)

    dense_req = AnnSearchRequest(
        data=[query_dense.tolist() if hasattr(query_dense, "tolist") else list(query_dense)],
        anns_field="vector",
        param={"metric_type": "COSINE", "params": {"nprobe": 16}},
        limit=candidate_limit,
    )

    sparse_payload = query_sparse if query_sparse else _EMPTY_SPARSE
    sparse_req = AnnSearchRequest(
        data=[sparse_payload],
        anns_field="sparse_vector",
        param={"metric_type": "IP", "params": {"drop_ratio_search": 0.2}},
        limit=candidate_limit,
    )

    ranker = WeightedRanker(dense_weight, sparse_weight)

    try:
        results = collection.hybrid_search(
            reqs=[dense_req, sparse_req],
            rerank=ranker,
            limit=top_k,
            output_fields=["template_id", "title", "objective", "variables"],
        )
    except MilvusException as exc:
        logger.warning("Hybrid search failed (%s). Falling back to dense-only.", exc)
        return search(query_dense, top_k=top_k, collection_name=collection_name)

    hits: list[dict] = []
    for hit in results[0]:
        hits.append({
            "id": hit.id,
            "template_id": hit.entity.get("template_id"),
            "title": hit.entity.get("title"),
            "objective": hit.entity.get("objective"),
            "variables": json.loads(hit.entity.get("variables", "[]")),
            "score": hit.score,
        })

    return hits
