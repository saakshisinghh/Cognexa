"""
apps/api/services/retrieval/bm25_retriever.py

Path A of triple retrieval: pure keyword (BM25) search.

REUSES the existing apps/api/weaviate_client.py connection from Phase 1 —
does not create a new Weaviate client or duplicate connection logic.
Only the QUERY MODE differs from Phase 1's hybrid search: this path forces
pure BM25 (zero vector weight) so it can be fused independently against
the vector-only path in rrf_fusion.py. Phase 1's combined hybrid search
(services/rag.py) is untouched and still used by anything that still
calls it directly.

VERIFIED against weaviate-client==4.7.1 (installed and introspected):
    - client.collections.get(name) -> Collection
    - collection.query.bm25(query=..., query_properties=[...], limit=...,
      filters=..., return_metadata=MetadataQuery(score=True)) -> QueryReturn
    - response.objects[i].uuid / .properties / .metadata.score
    - weaviate.classes.query.Filter.by_property(...).equal/contains_any/
      greater_or_equal/less_or_equal(...), combined with `&`

This replaces the old v3-only syntax (client.query.get(...).with_bm25(...)
.do()) and the raw v3 GraphQL `where` dict, both of which raised
`'WeaviateClient' object has no attribute 'query'` on a v4 client —
WeaviateClient has no `.query` attribute; queries live on
`client.collections.get(name).query` instead.

Field names match the extended DocumentChunk schema in
weaviate_client.py::ensure_schema (document_title, chunk_type, trust_score,
document_date, document_type, plant_id, asset_ids, text, page_number,
source, metadata). No changes required in copilot_v2.py — this module's
public function signature (bm25_retrieve(query, top_k, filters) ->
list[RetrievedChunk]) and the RetrievedChunk schema it returns are
unchanged from what services/retrieval/__init__.py already expects.
`_build_where_filter` and `_parse_date` are also imported directly by
vector_retriever.py — keep both defined in this module.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from weaviate.classes.query import Filter, MetadataQuery

from apps.api.weaviate_client import get_weaviate_client
from apps.api.schemas.retrieval import RetrievalFilters, RetrievedChunk

logger = logging.getLogger("indus_mind.retrieval.bm25")

_CHUNK_CLASS = "DocumentChunk"


async def bm25_retrieve(
    query: str,
    top_k: int,
    filters: RetrievalFilters,
) -> list[RetrievedChunk]:
    """
    Pure keyword search via Weaviate's BM25 mode.

    Raises on Weaviate connection failure — caller (_safe_call in
    services/retrieval/__init__.py) catches and degrades gracefully.
    """
    client = get_weaviate_client()
    collection = client.collections.get(_CHUNK_CLASS)

    where_filter = _build_where_filter(filters)

    response = collection.query.bm25(
        query=query,
        query_properties=["text"],
        limit=top_k,
        filters=where_filter,
        return_metadata=MetadataQuery(score=True),
    )

    chunks: list[RetrievedChunk] = []
    for rank, obj in enumerate(response.objects, start=1):
        props = obj.properties
        chunk_id = obj.uuid
        bm25_score = float(obj.metadata.score) if obj.metadata.score is not None else 0.0

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
        chunk.source_ranks["bm25"] = rank
        chunk.source_scores["bm25"] = bm25_score
        chunks.append(chunk)

    logger.debug("bm25_retrieve query=%r returned=%d", query, len(chunks))
    return chunks


def _build_where_filter(filters: RetrievalFilters) -> Optional[Filter]:
    """Translates RetrievalFilters into a Weaviate v4 Filter object."""
    operands = []

    if filters.document_type:
        operands.append(Filter.by_property("document_type").equal(filters.document_type))
    if filters.asset_id:
        operands.append(Filter.by_property("asset_ids").contains_any([str(filters.asset_id)]))
    if filters.plant_id:
        operands.append(Filter.by_property("plant_id").equal(str(filters.plant_id)))
    if filters.date_from:
        operands.append(
            Filter.by_property("document_date").greater_or_equal(
                datetime.fromisoformat(f"{filters.date_from.isoformat()}T00:00:00+00:00")
            )
        )
    if filters.date_to:
        operands.append(
            Filter.by_property("document_date").less_or_equal(
                datetime.fromisoformat(f"{filters.date_to.isoformat()}T23:59:59+00:00")
            )
        )
    if filters.min_trust_score > 0:
        operands.append(Filter.by_property("trust_score").greater_or_equal(filters.min_trust_score))

    if not operands:
        return None
    if len(operands) == 1:
        return operands[0]

    combined = operands[0]
    for op in operands[1:]:
        combined = combined & op
    return combined


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


class BM25RetrievalError(Exception):
    pass