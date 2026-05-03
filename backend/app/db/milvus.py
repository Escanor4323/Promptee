"""Milvus vector database client and collection schema.

Collection: prompt_templates
Fields: id, template_id, vector(384), title, objective, full_text, variables(JSON)
Index: IVF_FLAT on vector field
"""

import json
import logging
from typing import Optional

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, MilvusException, connections, utility

from app.config import get_settings

logger = logging.getLogger(__name__)

_collection: Optional[Collection] = None

COLLECTION_NAME = "prompt_templates"
VECTOR_DIM = 384


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


def get_or_create_collection() -> Collection:
    """Get or create the prompt_templates collection with proper schema."""
    global _collection

    if _collection is not None:
        return _collection

    connect()

    if utility.has_collection(COLLECTION_NAME):
        _collection = Collection(COLLECTION_NAME)
        logger.info("Loaded existing collection: %s", COLLECTION_NAME)
        return _collection

    id_field = FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True)
    template_id_field = FieldSchema(name="template_id", dtype=DataType.INT64)
    vector_field = FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM)
    title_field = FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=256)
    objective_field = FieldSchema(name="objective", dtype=DataType.VARCHAR, max_length=1024)
    variables_field = FieldSchema(name="variables", dtype=DataType.VARCHAR, max_length=1024)

    schema = CollectionSchema(
        fields=[id_field, template_id_field, vector_field, title_field, objective_field, variables_field],
        description="Prompt template vectors with metadata (full_text moved to SQLite)",
    )

    _collection = Collection(name=COLLECTION_NAME, schema=schema)

    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    _collection.create_index(field_name="vector", index_params=index_params)
    logger.info("Created collection %s with IVF_FLAT index", COLLECTION_NAME)

    return _collection


def insert_chunks(chunks: list, embeddings: list, template_ids: list[int]) -> list[int]:
    """Insert chunked documents with their embeddings into Milvus.

    Data is built as a list of row-level dicts (field_name -> value) so
    pymilvus binds values to the schema by name rather than positional
    column order. The auto_id `id` field is intentionally omitted.

    Returns list of inserted IDs.
    """
    collection = get_or_create_collection()

    if len(chunks) != len(template_ids):
        raise ValueError(
            f"insert_chunks: len(chunks)={len(chunks)} != len(template_ids)={len(template_ids)}"
        )
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"insert_chunks: len(chunks)={len(chunks)} != len(embeddings)={len(embeddings)}"
        )

    rows: list[dict] = []
    for chunk, embedding, template_id in zip(chunks, embeddings, template_ids):
        # Convert numpy arrays to plain python lists for pymilvus compatibility.
        vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        rows.append({
            "template_id": int(template_id),
            "vector": vector,
            "title": chunk.title,
            "objective": chunk.objective,
            "variables": json.dumps(chunk.variables),
        })

    result = collection.insert(rows)
    collection.flush()
    logger.info("Inserted %d chunks into Milvus", len(rows))
    return list(result.primary_keys)


def search(query_vector, top_k: int = 10) -> list[dict]:
    """Search for similar prompt templates.

    Returns list of dicts with: id, template_id, title, objective, variables, score.
    Note: full_text is fetched from SQLite during recommendation (see recommend.py).
    """
    collection = get_or_create_collection()

    # Fast path: If the collection is completely empty or not yet loaded into the
    # Milvus catalog, skip the search entirely.  `num_entities` can raise
    # MilvusException("collection not found") on a freshly-created collection
    # that has never had data inserted, so we treat any such error as empty.
    try:
        if collection.num_entities == 0:
            logger.info("Milvus collection is empty. Returning 0 results.")
            return []
    except MilvusException as exc:
        logger.info("Milvus collection not ready / empty (%s). Returning 0 results.", exc)
        return []

    collection.load()

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
    results = collection.search(
        data=[query_vector.tolist()],
        anns_field="vector",
        param=search_params,
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
