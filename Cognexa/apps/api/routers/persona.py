"""
apps/api/routers/persona.py

Phase 6 — AI Shadow Engineer API. Async (AsyncSession/get_async_db),
same convention as the other Phase 6 routers.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import get_async_db
from apps.api.models import User, UserRole
from apps.api.routers.auth import get_current_user
from apps.api.schemas.persona import (
    CaptureEntryRequest, ExpertKnowledgeEntrySummary, EntryListResponse,
    ExpertPersonaListResponse, ExpertPersonaSummary,
)
from apps.api.services import persona as persona_svc

logger = logging.getLogger("indus_mind.routers.persona")

router = APIRouter(prefix="/persona", tags=["AI Shadow Engineer"])


@router.post("/entries", response_model=ExpertKnowledgeEntrySummary, status_code=status.HTTP_201_CREATED)
async def capture_entry(
    body: CaptureEntryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Any authenticated user can capture their OWN expert knowledge —
    this is self-service tacit-knowledge capture, not an admin action.
    """
    entry = await persona_svc.capture_entry(
        db,
        author_user_id=current_user.id,
        title=body.title,
        content=body.content,
        asset_id=body.asset_id,
        tags=body.tags,
    )
    return entry


@router.get("/entries", response_model=EntryListResponse)
async def list_entries(
    author_user_id: str | None = Query(None),
    asset_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    entries = await persona_svc.list_entries(db, author_user_id=author_user_id, asset_id=asset_id)
    return EntryListResponse(entries=entries, total=len(entries))


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Soft-delete — only the author or an admin may remove an entry."""
    try:
        await persona_svc.deactivate_entry(
            db, entry_id, requesting_user_id=current_user.id, is_admin=(current_user.role == UserRole.admin),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/experts", response_model=ExpertPersonaListResponse)
async def list_experts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    The persona-selector UI's data source — every user who has captured
    at least one active expert-knowledge entry.
    """
    rows = await persona_svc.list_experts(db)
    experts = [ExpertPersonaSummary(user_id=uid, full_name=name, entry_count=count) for uid, name, count in rows]
    return ExpertPersonaListResponse(experts=experts)
