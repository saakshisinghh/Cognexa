"""
apps/api/routers/gap.py

Phase 6 — Knowledge Gap Detection API. Async (AsyncSession/get_async_db),
same convention as routers/temporal.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import get_async_db
from apps.api.models import User
from apps.api.routers.auth import get_current_user, require_engineer_or_admin
from apps.api.schemas.gap import AssetGapSummary, AssetGapListResponse, GapRecomputeTriggerResponse
from apps.api.services import gap as gap_svc
from apps.api.workers.gap_tasks import compute_knowledge_gaps_task

logger = logging.getLogger("indus_mind.routers.gap")

router = APIRouter(prefix="/gap", tags=["Knowledge Gap Detection"])


def _to_summary(gap_row, asset_name: str) -> AssetGapSummary:
    return AssetGapSummary(
        asset_id=gap_row.asset_id,
        asset_name=asset_name,
        gap_score=gap_row.gap_score,
        missing_categories=gap_row.missing_categories or [],
        present_categories=gap_row.present_categories or [],
        expected_categories=gap_row.expected_categories or [],
        incident_count=gap_row.incident_count,
        incident_penalty_applied=bool(gap_row.incident_penalty_applied),
        computed_at=gap_row.computed_at,
    )


@router.get("/assets", response_model=AssetGapListResponse)
async def list_asset_gaps(
    min_gap_score: float = Query(0.0, ge=0.0, le=1.0, description="Only return assets at or above this GapScore"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List assets sorted by GapScore descending — worst-documented first."""
    rows = await gap_svc.list_asset_gaps(db, min_gap_score=min_gap_score, limit=limit)
    summaries = [_to_summary(gap_row, asset_name) for gap_row, asset_name in rows]
    return AssetGapListResponse(assets=summaries, total=len(summaries))


@router.get("/assets/{asset_id}", response_model=AssetGapSummary)
async def get_asset_gap(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    row = await gap_svc.get_asset_gap(db, asset_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No knowledge gap data for asset {asset_id} yet — it may not have been "
                    f"processed by the nightly gap-detection job, or the asset_id is invalid.",
        )
    gap_row, asset_name = row
    return _to_summary(gap_row, asset_name)


@router.post("/recompute", response_model=GapRecomputeTriggerResponse)
async def trigger_gap_recompute(
    current_user: User = Depends(require_engineer_or_admin),
):
    """Manually queues the nightly gap-detection Celery task on-demand."""
    async_result = compute_knowledge_gaps_task.delay()
    logger.info("Manual gap recompute triggered by user_id=%s celery_id=%s", current_user.id, async_result.id)
    return GapRecomputeTriggerResponse(task_id=async_result.id)
