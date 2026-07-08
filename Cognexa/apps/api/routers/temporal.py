"""
apps/api/routers/temporal.py

Phase 6 — Temporal Knowledge Intelligence API.

Async throughout (AsyncSession / get_async_db) — matches the Phase 4
copilot router convention, not the sync Session/get_db convention used
by Phase 1 routers (auth.py, documents.py, assets.py). See
routers/copilot.py's module docstring for why both patterns coexist in
this codebase.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import get_async_db
from apps.api.models import User
from apps.api.routers.auth import get_current_user, require_engineer_or_admin
from apps.api.schemas.temporal import (
    ChunkTemporalInfo,
    SupersedeChunkRequest,
    StaleDocumentListResponse,
    StaleDocumentSummary,
    RecomputeTriggerResponse,
)
from apps.api.services import temporal as temporal_svc
from apps.api.workers.temporal_tasks import (
    recompute_trust_scores_task,
    flag_stale_documents_task,
    detect_superseded_chunks_task,
)

logger = logging.getLogger("indus_mind.routers.temporal")

router = APIRouter(prefix="/temporal", tags=["Temporal Knowledge Intelligence"])

_VALID_RECOMPUTE_TASKS = {
    "trust_scores": recompute_trust_scores_task,
    "stale_documents": flag_stale_documents_task,
    "superseded_chunks": detect_superseded_chunks_task,
}


@router.get("/chunks/{chunk_id}", response_model=ChunkTemporalInfo)
async def get_chunk_temporal_info(
    chunk_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    chunk = await temporal_svc.get_chunk_temporal_info(db, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chunk {chunk_id} not found.")

    return ChunkTemporalInfo(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        trust_score=chunk.trust_score,
        valid_from=chunk.valid_from,
        valid_to=chunk.valid_to,
        superseded_by_chunk_id=chunk.superseded_by_chunk_id,
        decay_computed_at=chunk.decay_computed_at,
    )


@router.patch("/chunks/{chunk_id}/supersede", response_model=ChunkTemporalInfo)
async def supersede_chunk(
    chunk_id: str,
    body: SupersedeChunkRequest,
    current_user: User = Depends(require_engineer_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Manual override — see services/temporal.py::mark_chunk_superseded docstring."""
    try:
        chunk = await temporal_svc.mark_chunk_superseded(db, chunk_id, body.superseded_by_chunk_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ChunkTemporalInfo(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        trust_score=chunk.trust_score,
        valid_from=chunk.valid_from,
        valid_to=chunk.valid_to,
        superseded_by_chunk_id=chunk.superseded_by_chunk_id,
        decay_computed_at=chunk.decay_computed_at,
    )


@router.get("/documents/stale", response_model=StaleDocumentListResponse)
async def list_stale_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    documents = await temporal_svc.list_stale_documents(db)
    summaries = [
        StaleDocumentSummary(
            document_id=d.id,
            original_filename=d.original_filename,
            category=d.category,
            is_stale=d.is_stale,
            stale_flagged_at=d.stale_flagged_at,
            stale_reason=d.stale_reason,
        )
        for d in documents
    ]
    return StaleDocumentListResponse(documents=summaries, total=len(summaries))


@router.post("/recompute", response_model=RecomputeTriggerResponse)
async def trigger_recompute(
    task: str = "trust_scores",
    current_user: User = Depends(require_engineer_or_admin),
):
    """
    Manually queues one of the nightly Phase 6 Celery tasks on-demand
    (useful for testing, or forcing a recompute right after a bulk
    document upload rather than waiting for the nightly schedule).

    `task` must be one of: trust_scores, stale_documents, superseded_chunks.
    """
    celery_task = _VALID_RECOMPUTE_TASKS.get(task)
    if celery_task is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown task '{task}'. Must be one of: {sorted(_VALID_RECOMPUTE_TASKS)}.",
        )

    async_result = celery_task.delay()
    logger.info("Manual recompute triggered by user_id=%s task=%s celery_id=%s", current_user.id, task, async_result.id)

    return RecomputeTriggerResponse(task_id=async_result.id, task_name=task)
