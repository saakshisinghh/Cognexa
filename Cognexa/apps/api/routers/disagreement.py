"""
apps/api/routers/disagreement.py

Phase 6 — Expert Disagreement Detection API. Async (AsyncSession/
get_async_db), same convention as routers/temporal.py, gap.py, loss.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import get_async_db
from apps.api.models import User
from apps.api.routers.auth import get_current_user, require_engineer_or_admin
from apps.api.schemas.disagreement import (
    DisagreementSummary, DisagreementListResponse,
    ResolveDisagreementRequest, DisagreementRecomputeTriggerResponse,
)
from apps.api.services import disagreement as disagreement_svc
from apps.api.workers.disagreement_tasks import detect_expert_disagreements_task

logger = logging.getLogger("indus_mind.routers.disagreement")

router = APIRouter(prefix="/disagreements", tags=["Expert Disagreement Detection"])


def _to_summary(d, asset_name=None) -> DisagreementSummary:
    return DisagreementSummary(
        id=d.id,
        asset_id=d.asset_id,
        asset_name=asset_name,
        topic=d.topic,
        document_a_id=d.document_a_id,
        document_a_title=d.document_a_title,
        document_b_id=d.document_b_id,
        document_b_title=d.document_b_title,
        occurrence_count=d.occurrence_count,
        max_severity=d.max_severity,
        sample_excerpt_a=d.sample_excerpt_a,
        sample_excerpt_b=d.sample_excerpt_b,
        last_seen_at=d.last_seen_at,
        is_resolved=d.is_resolved,
        resolved_by_user_id=d.resolved_by_user_id,
        resolved_at=d.resolved_at,
        resolution_notes=d.resolution_notes,
    )


@router.get("", response_model=DisagreementListResponse)
async def list_disagreements(
    include_resolved: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List disagreement clusters across all assets, sorted by occurrence_count descending."""
    rows = await disagreement_svc.list_disagreements(db, include_resolved=include_resolved, limit=limit)
    summaries = [_to_summary(d, asset_name) for d, asset_name in rows]
    return DisagreementListResponse(disagreements=summaries, total=len(summaries))


@router.get("/assets/{asset_id}", response_model=DisagreementListResponse)
async def get_asset_disagreements(
    asset_id: str,
    include_resolved: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    rows = await disagreement_svc.get_asset_disagreements(db, asset_id, include_resolved=include_resolved)
    summaries = [_to_summary(d) for d in rows]
    return DisagreementListResponse(disagreements=summaries, total=len(summaries))


@router.patch("/{disagreement_id}/resolve", response_model=DisagreementSummary)
async def resolve_disagreement(
    disagreement_id: str,
    body: ResolveDisagreementRequest,
    current_user: User = Depends(require_engineer_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Marks a disagreement cluster resolved. Note: the nightly task will
    automatically REOPEN this if a new occurrence of the same
    (asset, document pair, topic) contradiction appears in query_history
    after this resolved_at timestamp — see workers/disagreement_tasks.py.
    """
    try:
        d = await disagreement_svc.resolve_disagreement(db, disagreement_id, current_user.id, body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_summary(d)


@router.post("/recompute", response_model=DisagreementRecomputeTriggerResponse)
async def trigger_disagreement_recompute(
    current_user: User = Depends(require_engineer_or_admin),
):
    async_result = detect_expert_disagreements_task.delay()
    logger.info("Manual disagreement recompute triggered by user_id=%s celery_id=%s", current_user.id, async_result.id)
    return DisagreementRecomputeTriggerResponse(task_id=async_result.id)
