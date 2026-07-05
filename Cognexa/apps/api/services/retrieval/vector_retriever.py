"""
apps/api/services/retrieval/vector_retriever.py

Path B of triple retrieval: pure semantic (vector) search.

REUSES apps/api/services/embedder.py (Sentence Transformers, loaded once
at Phase 1 startup) and apps/api/weaviate_client.py — does not load a
second embedding model or open a second Weaviate connection.

VERIFIED against weaviate-client==4.7.1 (installed and introspected):
    - client.collections.get(name) -> Collection
    - collection.query.near_vector(near_vector=..., limit=..., filters=...,
      return_metadata=MetadataQuery(distance=True)) -> QueryReturn
    - response.objects[i].uuid / .properties / .metadata.distance

This replaces the old v3-only syntax (client.query.get(...).with_near_vector(
...).do()) that raised `'WeaviateClient' object has no attribute 'query'`
on a v4 client — WeaviateClient has no `.query` attribute; queries live on
`client.collections.get(name).query` instead.

Field names match the extended DocumentChunk schema in
weaviate_client.py::ensure_schema (document_title, chunk_type, trust_score,
document_date, document_type, plant_id, asset_ids, text, page_number,
source, metadata). No changes required in copilot_v2.py — this module's
public function signature (vector_retrieve(query, top_k, filters) ->
list[RetrievedChunk]) and the RetrievedChunk schema it returns are
unchanged from what services/retrieval/__init__.py already expects.
"""

import logging
from typing import Optional
from uuid import UUID

from weaviate.classes.query import MetadataQuery

from apps.api.services.embedder import encode_query
from apps.api.weaviate_client import get_weaviate_client
from apps.api.schemas.retrieval import RetrievalFilters, RetrievedChunk
from apps.api.services.retrieval.bm25_retriever import _build_where_filter, _parse_date

logger = logging.getLogger("indus_mind.retrieval.vector")

_CHUNK_CLASS = "DocumentChunk"


async def vector_retrieve(
    query: str,
    top_k: int,
    filters: RetrievalFilters,
) -> list[RetrievedChunk]:
    """
    Pure nearest-neighbor vector search via Weaviate.

    Raises on embedding failure or Weaviate connection failure; caller
    degrades gracefully (see services/retrieval/__init__.py::_safe_call).
    """
    query_vector = encode_query(query)  # existing Phase 1 embedder.py function

    client = get_weaviate_client()
    collection = client.collections.get(_CHUNK_CLASS)
    where_filter = _build_where_filter(filters)

    response = collection.query.near_vector(
        near_vector=query_vector if isinstance(query_vector, list) else query_vector.tolist(),
        limit=top_k,
        filters=where_filter,
        return_metadata=MetadataQuery(distance=True),
    )

    chunks: list[RetrievedChunk] = []
    for rank, obj in enumerate(response.objects, start=1):
        props = obj.properties
        chunk_id = obj.uuid
        distance = float(obj.metadata.distance) if obj.metadata.distance is not None else 1.0
        # Weaviate cosine distance: 0 = identical, 2 = opposite. Convert to
        # a 0..1 similarity score (higher = better) for uniform scoring
        # alongside BM25's score in rrf_fusion.py.
        similarity = max(0.0, 1.0 - (distance / 2.0))

        if not chunk_id:
            continue

        chunk = RetrievedChunk(
            chunk_id=chunk_id,
            document_id=props.get("document_id"),
            document_title=props.get("document_title") or "Untitled Document",
            content=props.get("text", ""),
            page_number=props.get("page_number"),
            chunk_type=props.get("chunk_type"),
            trust_score=float(props.get("trust_score") or 1.0),
            document_date=_parse_date(props.get("document_date")),
            asset_ids=[UUID(a) for a in (props.get("asset_ids") or []) if a],
        )
        chunk.source_ranks["vector"] = rank
        chunk.source_scores["vector"] = similarity
        chunks.append(chunk)

    logger.debug("vector_retrieve query=%r returned=%d", query, len(chunks))
    return chunks


class VectorRetrievalError(Exception):
    pass