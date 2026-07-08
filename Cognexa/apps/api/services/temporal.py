"""
apps/api/services/temporal.py

Phase 6 — Temporal Knowledge Intelligence.

Async, DB-facing service used by routers/temporal.py (FastAPI, AsyncSession).
The nightly batch equivalents live in workers/temporal_tasks.py (sync
Celery, SessionLocal) — that module is where full-table recomputation and
the supersession-detection sweep actually run; this module handles the
on-demand, single-record API paths (look up one chunk's temporal info,
manually mark a chunk superseded, list currently-stale documents).

Both this module and workers/temporal_tasks.py call the same
`push_trust_score_to_weaviate()` helper below, so there is one place that
knows how to keep Postgres and Weaviate in sync — not two.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import Chunk, Document
from apps.api.services import decay
from apps.api.weaviate_client import get_weaviate_client

logger = logging.getLogger("indus_mind.temporal")

_CHUNK_CLASS = "DocumentChunk"


def push_trust_score_to_weaviate(weaviate_id: Optional[str], trust_score: float) -> None:
    """
    Writes the recomputed trust_score onto the corresponding Weaviate
    object, so retrieval-time filtering (bm25_retriever.py /
    vector_retriever.py's `min_trust_score` filter, and the value
    surfaced in RetrievedChunk.trust_score) reflects the decayed value —
    not just whatever trust_score was set at ingestion time.

    Uses the SYNC WeaviateClient returned by get_weaviate_client() (the
    v4 client instantiated via weaviate.connect_to_custom is blocking,
    not an AsyncClient) — safe to call directly from a Celery task, and
    wrapped in asyncio.to_thread() by the async callers in this module
    so it never blocks the event loop.

    No-op (with a warning) if weaviate_id is missing — this can happen
    for chunks ingested before embedding finished, or in test fixtures.
    """
    if not weaviate_id:
        logger.warning("push_trust_score_to_weaviate called with no weaviate_id — skipping")
        return
    try:
        client = get_weaviate_client()
        collection = client.collections.get(_CHUNK_CLASS)
        collection.data.update(uuid=weaviate_id, properties={"trust_score": trust_score})
    except Exception as exc:  # noqa: BLE001
        # Postgres is the source of truth; a Weaviate sync failure here
        # must not fail the caller's transaction — retrieval will simply
        # use a stale trust_score in Weaviate until the next nightly run
        # (or the next manual recompute) succeeds.
        logger.warning("Failed to push trust_score to Weaviate weaviate_id=%s error=%s", weaviate_id, exc)


async def get_chunk_temporal_info(db: AsyncSession, chunk_id: str) -> Optional[Chunk]:
    result = await db.execute(select(Chunk).where(Chunk.id == chunk_id))
    return result.scalar_one_or_none()


async def mark_chunk_superseded(
    db: AsyncSession,
    chunk_id: str,
    superseded_by_chunk_id: str,
) -> Chunk:
    """
    Manual override — an engineer explicitly marks chunk_id as replaced
    by superseded_by_chunk_id (e.g. "this procedure section was revised
    in the new manual"). Automatic detection (via Weaviate near-neighbor
    similarity across an asset's documents) runs nightly in
    workers/temporal_tasks.py::detect_superseded_chunks_task — this is
    the human-in-the-loop complement to that, for cases the automatic
    similarity sweep misses or gets wrong.

    Raises ValueError if either chunk_id doesn't exist, or if
    superseded_by_chunk_id == chunk_id (a chunk cannot supersede itself).
    """
    if chunk_id == superseded_by_chunk_id:
        raise ValueError("A chunk cannot supersede itself.")

    chunk = await get_chunk_temporal_info(db, chunk_id)
    if chunk is None:
        raise ValueError(f"Chunk {chunk_id} not found.")

    new_chunk_result = await db.execute(select(Chunk.id).where(Chunk.id == superseded_by_chunk_id))
    if new_chunk_result.scalar_one_or_none() is None:
        raise ValueError(f"Superseding chunk {superseded_by_chunk_id} not found.")

    now = datetime.now(timezone.utc)
    chunk.valid_to = now
    chunk.superseded_by_chunk_id = superseded_by_chunk_id
    chunk.trust_score = decay.compute_trust_score(chunk.valid_from, chunk.valid_to, None, now=now)
    chunk.decay_computed_at = now

    await db.commit()
    await db.refresh(chunk)

    await asyncio.to_thread(push_trust_score_to_weaviate, chunk.weaviate_id, chunk.trust_score)

    return chunk


async def list_stale_documents(db: AsyncSession, threshold: float = 0.4) -> list[Document]:
    """
    Returns documents currently flagged `is_stale=True` (set by the
    nightly workers/temporal_tasks.py::flag_stale_documents_task).
    `threshold` is accepted for API symmetry/documentation but does not
    re-filter here — is_stale is precomputed nightly using this same
    default threshold; pass a different threshold to
    POST /temporal/recompute if you need an ad-hoc re-evaluation instead
    of waiting for the next nightly run.
    """
    result = await db.execute(select(Document).where(Document.is_stale.is_(True)))
    return list(result.scalars().all())
