"""
Search Router — Semantic and hybrid search across documents and assets.
"""
from __future__ import annotations
import logging
import time
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.models import Document, Asset, User
from apps.api.routers.auth import get_current_user
from apps.api.schemas import SearchRequest, SearchResponse, SearchResult
from apps.api.services.embedder import embed_texts
from apps.api.weaviate_client import get_weaviate_client, CHUNK_CLASS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["Search"])


def _highlight_snippet(text: str, query: str, window: int = 200) -> str:
    """Extract a relevant snippet with simple keyword highlighting."""
    lower_text = text.lower()
    lower_query = query.lower()
    words = lower_query.split()

    # Find first keyword match position
    best_pos = 0
    for word in words:
        pos = lower_text.find(word)
        if pos >= 0:
            best_pos = pos
            break

    start = max(0, best_pos - window // 2)
    end = min(len(text), start + window)
    snippet = text[start:end].strip()

    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"

    return snippet


@router.post("", response_model=SearchResponse)
def semantic_search(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start_time = time.time()

    if not payload.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    # Embed query
    try:
        query_vector = embed_texts([payload.query])[0]
    except Exception as e:
        logger.error(f"Query embedding failed: {e}")
        raise HTTPException(500, "Failed to embed query")

    # Build Weaviate filter
    from weaviate.classes.query import MetadataQuery, Filter

    filters = None
    if payload.asset_id:
        filters = Filter.by_property("asset_id").equal(payload.asset_id)
    elif payload.document_ids:
        if len(payload.document_ids) == 1:
            filters = Filter.by_property("document_id").equal(payload.document_ids[0])
        else:
            filters = Filter.by_property("document_id").contains_any(payload.document_ids)

    try:
        wv_client = get_weaviate_client()
        collection = wv_client.collections.get(CHUNK_CLASS)
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=payload.top_k,
            return_metadata=MetadataQuery(distance=True),
            filters=filters,
        )
        raw_results = response.objects
    except Exception as e:
        logger.error(f"Weaviate search error: {e}")
        raise HTTPException(500, "Search service unavailable")

    # Enrich with DB data
    results: List[SearchResult] = []
    for obj in raw_results:
        score = round(1.0 - (obj.metadata.distance or 0.0), 4)
        if score < payload.min_score:
            continue

        doc_id = obj.properties.get("document_id", "")
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            continue

        # Apply category/tag filter
        if payload.category and doc.category != payload.category:
            continue
        if payload.tags:
            doc_tags = doc.tags or []
            if not any(t in doc_tags for t in payload.tags):
                continue

        asset_name = None
        if doc.asset_id:
            asset = db.query(Asset).filter(Asset.id == doc.asset_id).first()
            if asset:
                asset_name = asset.name

        text = obj.properties.get("text", "")
        highlight = _highlight_snippet(text, payload.query)

        results.append(SearchResult(
            chunk_id=str(obj.uuid),
            document_id=doc_id,
            document_name=doc.original_filename,
            asset_id=doc.asset_id,
            asset_name=asset_name,
            text=text,
            score=score,
            page_number=obj.properties.get("page_number"),
            chunk_index=obj.properties.get("chunk_index", 0),
            highlight=highlight,
        ))

    elapsed = round((time.time() - start_time) * 1000, 2)

    return SearchResponse(
        query=payload.query,
        results=results,
        total=len(results),
        took_ms=elapsed,
    )


@router.get("/suggest")
def search_suggestions(
    q: str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=10),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return document names and categories matching the query prefix."""
    docs = (
        db.query(Document.original_filename, Document.category)
        .filter(Document.original_filename.ilike(f"%{q}%"))
        .limit(limit)
        .all()
    )
    suggestions = [{"text": d.original_filename, "type": "document"} for d in docs]
    return {"suggestions": suggestions}
