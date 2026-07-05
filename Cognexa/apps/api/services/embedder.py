"""
Embedder Service — Sentence-Transformers batch embedding with Weaviate storage.
"""
from __future__ import annotations
import logging
import uuid
import json
from typing import List, Optional
import numpy as np

from apps.api.config import settings
from apps.api.services.chunker import TextChunk

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(settings.EMBEDDING_MODEL)
            logger.info(f"Embedding model loaded: {settings.EMBEDDING_MODEL}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    return _model


def embed_texts(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """
    Embed a list of texts in batches.
    Returns list of normalized float vectors.
    """
    if not texts:
        return []

    model = _get_model()
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            embeddings = model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            all_embeddings.extend(embeddings.tolist())
        except Exception as e:
            logger.error(f"Embedding batch {i//batch_size} failed: {e}")
            # Return zero vectors as fallback
            dim = settings.EMBEDDING_DIMENSION
            all_embeddings.extend([[0.0] * dim for _ in batch])

    return all_embeddings


def embed_and_store_chunks(
    chunks: List[TextChunk],
    document_id: str,
    asset_id: Optional[str],
    source: str,
    weaviate_client,
    batch_size: int = 32,
) -> List[str]:
    """
    Embed chunks and store them in Weaviate.
    Returns list of Weaviate UUIDs.
    """
    if not chunks:
        return []

    from apps.api.weaviate_client import CHUNK_CLASS

    texts = [c.text for c in chunks]
    embeddings = embed_texts(texts, batch_size=batch_size)

    collection = weaviate_client.collections.get(CHUNK_CLASS)
    weaviate_ids: List[str] = []

    # Batch upsert to Weaviate
    with collection.batch.dynamic() as batch:
        for chunk, embedding in zip(chunks, embeddings):
            wv_id = str(uuid.uuid4())
            try:
                batch.add_object(
                    properties={
                        "document_id": document_id,
                        "asset_id": asset_id or "",
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.text,
                        "page_number": chunk.page_number or 0,
                        "source": source,
                        "metadata": json.dumps(chunk.metadata),
                    },
                    vector=embedding,
                    uuid=wv_id,
                )
                weaviate_ids.append(wv_id)
            except Exception as e:
                logger.error(f"Failed to store chunk {chunk.chunk_index} in Weaviate: {e}")
                weaviate_ids.append("")

    logger.info(
        f"Stored {len(weaviate_ids)} embeddings in Weaviate for document {document_id}"
    )
    return weaviate_ids


def delete_document_embeddings(document_id: str, weaviate_client) -> int:
    """Delete all Weaviate vectors for a document."""
    from apps.api.weaviate_client import CHUNK_CLASS
    from weaviate.classes.query import Filter

    try:
        collection = weaviate_client.collections.get(CHUNK_CLASS)
        result = collection.data.delete_many(
            where=Filter.by_property("document_id").equal(document_id)
        )
        count = result.successful if result else 0
        logger.info(f"Deleted {count} embeddings for document {document_id}")
        return count
    except Exception as e:
        logger.error(f"Failed to delete embeddings for {document_id}: {e}")
        return 0

def encode_query(text: str) -> list[float]:
    """
    Encode a single query using the shared SentenceTransformer model.
    Returns a normalized embedding vector.
    """
    model = _get_model()

    embedding = model.encode(
        text,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    return embedding.tolist()