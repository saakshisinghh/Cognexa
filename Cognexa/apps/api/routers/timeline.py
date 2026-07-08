"""
apps/api/routers/timeline.py

Phase 6 — Failure Time Machine API. Async (AsyncSession/get_async_db).
Pure read-path — no Celery task, no new tables (see services/timeline.py
module docstring).
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import get_async_db
from apps.api.models import User
from apps.api.routers.auth import get_current_user
from apps.api.schemas.timeline import AssetTimelineResponse, AssetStateSnapshot
from apps.api.services import timeline as timeline_svc

router = APIRouter(prefix="/timeline", tags=["Failure Time Machine"])


@router.get("/assets/{asset_id}", response_model=AssetTimelineResponse)
async def get_asset_timeline(
    asset_id: str,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    asset, events = await timeline_svc.get_asset_timeline(db, asset_id, start_date, end_date)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset {asset_id} not found.")
    return AssetTimelineResponse(asset_id=asset.id, asset_name=asset.name, events=events, total=len(events))


@router.get("/assets/{asset_id}/replay", response_model=AssetStateSnapshot)
async def replay_asset_state(
    asset_id: str,
    as_of: datetime = Query(..., description="Reconstruct asset knowledge/incident state as of this timestamp"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    result = await timeline_svc.get_asset_state_at(db, asset_id, as_of)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset {asset_id} not found.")
    asset, valid_chunks, incidents, doc_count = result
    return AssetStateSnapshot(
        asset_id=asset.id,
        asset_name=asset.name,
        as_of=as_of,
        valid_chunks=valid_chunks,
        incidents_to_date=incidents,
        documents_existing_to_date=doc_count,
    )
