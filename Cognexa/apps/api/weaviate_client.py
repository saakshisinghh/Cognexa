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
    """Ensure the DocumentChunk collection exists in Weaviate."""
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
                    Property(name="asset_id", data_type=DataType.TEXT),
                    Property(name="chunk_index", data_type=DataType.INT),
                    Property(name="text", data_type=DataType.TEXT),
                    Property(name="page_number", data_type=DataType.INT),
                    Property(name="source", data_type=DataType.TEXT),
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
