"""
apps/api/routers/loss.py

Phase 6 — Knowledge Loss Prediction API. Async (AsyncSession/get_async_db),
same convention as routers/temporal.py and routers/gap.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import get_async_db
from apps.api.models import User
from apps.api.routers.auth import get_current_user, require_admin
from apps.api.schemas.loss import (
    AssetRiskSummary, AssetRiskListResponse, AssetOwnerSummary, AssetOwnersResponse,
    SetRetirementFlagRequest, LossRecomputeTriggerResponse,
)
from apps.api.services import loss as loss_svc
from apps.api.workers.loss_tasks import compute_knowledge_loss_risk_task

logger = logging.getLogger("indus_mind.routers.loss")

router = APIRouter(prefix="/loss", tags=["Knowledge Loss Prediction"])


@router.get("/assets", response_model=AssetRiskListResponse)
async def list_asset_risks(
    min_risk_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List assets sorted by knowledge-loss risk_score descending."""
    from sqlalchemy import select as _select  # local import to keep this function self-contained

    rows = await loss_svc.list_asset_risks(db, min_risk_score=min_risk_score, limit=limit)

    owner_ids = {r.primary_owner_user_id for r, _ in rows if r.primary_owner_user_id}
    owner_names: dict[str, str] = {}
    if owner_ids:
        result = await db.execute(_select(User.id, User.full_name).where(User.id.in_(owner_ids)))
        owner_names = {uid: name for uid, name in result.all()}

    summaries = [
        _to_summary(risk_row, asset_name, owner_names.get(risk_row.primary_owner_user_id))
        for risk_row, asset_name in rows
    ]
    return AssetRiskListResponse(assets=summaries, total=len(summaries))


@router.get("/assets/{asset_id}", response_model=AssetRiskSummary)
async def get_asset_risk(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    row = await loss_svc.get_asset_risk(db, asset_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No knowledge loss risk data for asset {asset_id} yet — "
                    f"it may not have been processed by the nightly job.",
        )
    risk_row, asset_name, owner_name = row
    return _to_summary(risk_row, asset_name, owner_name)


@router.get("/assets/{asset_id}/owners", response_model=AssetOwnersResponse)
async def get_asset_owners(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    rows = await loss_svc.list_asset_owners(db, asset_id)
    owners = [
        AssetOwnerSummary(
            user_id=o.user_id,
            full_name=name,
            document_count=o.document_count,
            incident_count=o.incident_count,
            ownership_score=o.ownership_score,
            is_primary_owner=o.is_primary_owner,
            last_activity_at=o.last_activity_at,
        )
        for o, name in rows
    ]
    return AssetOwnersResponse(asset_id=asset_id, owners=owners)


@router.patch("/users/{user_id}/retirement-flag", response_model=dict)
async def set_retirement_flag(
    user_id: str,
    body: SetRetirementFlagRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Admin-only — manually flags a user as a retirement/departure risk,
    based on HR knowledge this system has no other way to know. Boosts
    the risk_score for any asset where this user is the primary owner
    on the next nightly recompute (or immediate POST /loss/recompute).
    """
    try:
        user = await loss_svc.set_user_retirement_flag(db, user_id, body.is_retirement_risk, body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    logger.info(
        "Retirement flag set by admin_id=%s target_user_id=%s flagged=%s",
        current_user.id, user_id, body.is_retirement_risk,
    )
    return {"user_id": user.id, "is_retirement_risk": user.is_retirement_risk}


@router.post("/recompute", response_model=LossRecomputeTriggerResponse)
async def trigger_loss_recompute(
    current_user: User = Depends(require_admin),
):
    async_result = compute_knowledge_loss_risk_task.delay()
    logger.info("Manual loss recompute triggered by user_id=%s celery_id=%s", current_user.id, async_result.id)
    return LossRecomputeTriggerResponse(task_id=async_result.id)


def _to_summary(risk_row, asset_name: str, owner_name) -> AssetRiskSummary:
    return AssetRiskSummary(
        asset_id=risk_row.asset_id,
        asset_name=asset_name,
        primary_owner_user_id=risk_row.primary_owner_user_id,
        primary_owner_name=owner_name,
        concentration_score=risk_row.concentration_score,
        contributor_count=risk_row.contributor_count,
        retirement_boost_applied=risk_row.retirement_boost_applied,
        risk_score=risk_row.risk_score,
        risk_level=risk_row.risk_level,
        mitigation_recommendation=risk_row.mitigation_recommendation,
        computed_at=risk_row.computed_at,
    )
