import weaviate
from weaviate.auth import AuthApiKey
from apps.api.config import settings
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_client: Optional[weaviate.WeaviateClient] = None

CHUNK_CLASS = "DocumentChunk"


def get_weaviate_client() -> weaviate.WeaviateClient:
    """Get or create the Weaviate client singleton."""
    global _client
    if _client is None:
        try:
            connect_kwargs = {}
            if settings.WEAVIATE_API_KEY:
                connect_kwargs["auth_credentials"] = AuthApiKey(settings.WEAVIATE_API_KEY)

            _client = weaviate.connect_to_custom(
                http_host=settings.WEAVIATE_URL.replace("http://", "").replace("https://", "").split(":")[0],
                http_port=int(settings.WEAVIATE_URL.split(":")[-1]) if ":" in settings.WEAVIATE_URL else 8080,
                http_secure=settings.WEAVIATE_URL.startswith("https"),
                grpc_host=settings.WEAVIATE_URL.replace("http://", "").replace("https://", "").split(":")[0],
                grpc_port=50051,
                grpc_secure=False,
                **connect_kwargs,
            )
            logger.info("Weaviate client connected")
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            raise
    return _client


def get_weaviate_dependency():
    """FastAPI dependency for Weaviate client."""
    client = get_weaviate_client()
    try:
        yield client
    finally:
        pass


def ensure_schema(client: weaviate.WeaviateClient) -> None:
    """
    Ensure the DocumentChunk collection exists in Weaviate.

    NOTE — Phase 4 schema update:
    The original Phase 1 schema only carried (document_id, asset_id,
    chunk_index, text, page_number, source, metadata). Phase 4's triple
    retrieval (bm25_retriever.py / vector_retriever.py) needs several of
    these as first-class, filterable/queryable properties instead of
    being buried inside the opaque `metadata` text blob:

        - document_title  (shown in citations / UI)
        - chunk_type       (used by the reranker / context assembler)
        - trust_score      (used by trust_filter.py + min_trust_score filter)
        - document_date    (used by temporal_boost.py + date_from/date_to filter)
        - document_type    (used by RetrievalFilters.document_type)
        - plant_id         (used by RetrievalFilters.plant_id)
        - asset_ids        (renamed from singular `asset_id` -> TEXT_ARRAY,
                             since a chunk can reference more than one asset
                             and retrieval code/tests already assume a list)

    If you already have data indexed under the old schema, this will only
    apply to newly-created collections (Weaviate does not let you rename/
    retype existing properties in place) — existing deployments need a
    reindex. See the migration note at the bottom of this file.
    """
    try:
        if not client.collections.exists(CHUNK_CLASS):
            from weaviate.classes.config import Configure, Property, DataType, VectorDistances
            client.collections.create(
                name=CHUNK_CLASS,
                description="Document text chunks with embeddings",
                vectorizer_config=Configure.Vectorizer.none(),
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE
                ),
                properties=[
                    Property(name="document_id", data_type=DataType.TEXT),
                    Property(name="document_title", data_type=DataType.TEXT),
                    Property(name="document_type", data_type=DataType.TEXT),
                    Property(name="document_date", data_type=DataType.DATE),
                    Property(name="chunk_index", data_type=DataType.INT),
                    Property(name="chunk_type", data_type=DataType.TEXT),
                    Property(name="text", data_type=DataType.TEXT),
                    Property(name="page_number", data_type=DataType.INT),
                    Property(name="source", data_type=DataType.TEXT),
                    Property(name="trust_score", data_type=DataType.NUMBER),
                    Property(name="plant_id", data_type=DataType.TEXT),
                    Property(name="asset_ids", data_type=DataType.TEXT_ARRAY),
                    Property(name="metadata", data_type=DataType.TEXT),
                ],
            )
            logger.info(f"Created Weaviate collection: {CHUNK_CLASS}")
        else:
            logger.info(f"Weaviate collection {CHUNK_CLASS} already exists")
    except Exception as e:
        logger.error(f"Failed to ensure Weaviate schema: {e}")
        raise


def close_weaviate_client() -> None:
    """Close the Weaviate client."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("Weaviate client closed")


# ---------------------------------------------------------------------------
# Migration note (run once, manually, against an existing deployment):
#
#   If DocumentChunk already exists with the old Phase 1 properties
#   (document_id, asset_id, chunk_index, text, page_number, source, metadata),
#   Weaviate will NOT auto-add the new properties above just by redeploying
#   this file, and it will not auto-rename asset_id -> asset_ids. Options:
#
#   1. Fresh environment / no production data yet (most likely for this
#      project right now): drop and recreate the collection so
#      ensure_schema() creates it with the full property set:
#
#        client.collections.delete("DocumentChunk")
#        ensure_schema(client)
#        # then re-run the ingestion pipeline (PDF -> OCR -> chunks -> embeddings)
#
#   2. Existing data you must keep: add the missing properties with
#      client.collections.get("DocumentChunk").config.add_property(...)
#      for each new field, then backfill values for existing objects
#      via client.collections.get("DocumentChunk").data.update(...).
#      asset_id -> asset_ids requires reading each object's old asset_id
#      and writing it back as a single-element list under asset_ids.
# ---------------------------------------------------------------------------