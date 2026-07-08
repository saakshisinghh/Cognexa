"""
apps/api/services/timeline.py

Phase 6 — Failure Time Machine.

No new tables, no nightly job — this is a pure read-time aggregation of
data that already exists:
    Incident   (Phase 3)
    Document   (Phase 1) — "work_order"/"inspection" are just
               Document.category values; there is no dedicated
               WorkOrder/Inspection model in this codebase (see the
               module docstring discussion earlier in this project).
    Chunk      (Phase 1) + valid_from/valid_to (Phase 6 Feature 1) —
               used for the point-in-time replay.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import Asset, Document, Chunk
from apps.api.models.incident import Incident
from apps.api.schemas.timeline import (
    TimelineEvent, ReplayChunkState, ReplayIncidentState,
)

# Document.category values treated as their own timeline event types
# rather than the generic "document" bucket — purely cosmetic (affects
# event_type label only), since there's no separate table backing them.
_SPECIAL_DOCUMENT_CATEGORIES = {"work_order", "inspection"}


async def get_asset_timeline(
    db: AsyncSession,
    asset_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> tuple[Optional[Asset], list[TimelineEvent]]:
    asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = asset_result.scalar_one_or_none()
    if asset is None:
        return None, []

    events: list[TimelineEvent] = []

    incident_query = select(Incident).where(Incident.asset_id == asset_id)
    if start_date:
        incident_query = incident_query.where(Incident.occurred_at >= start_date)
    if end_date:
        incident_query = incident_query.where(Incident.occurred_at <= end_date)
    incidents = (await db.execute(incident_query)).scalars().all()

    for inc in incidents:
        events.append(TimelineEvent(
            event_type="incident",
            occurred_at=inc.occurred_at,
            title=inc.title,
            description=inc.description,
            severity=inc.severity.value if hasattr(inc.severity, "value") else str(inc.severity),
            source_id=inc.id,
            source_url_hint=f"/incidents/{inc.id}",
        ))

    doc_query = select(Document).where(Document.asset_id == asset_id)
    if start_date:
        doc_query = doc_query.where(Document.created_at >= start_date)
    if end_date:
        doc_query = doc_query.where(Document.created_at <= end_date)
    documents = (await db.execute(doc_query)).scalars().all()

    for doc in documents:
        event_type = doc.category if doc.category in _SPECIAL_DOCUMENT_CATEGORIES else "document"
        events.append(TimelineEvent(
            event_type=event_type,
            occurred_at=doc.created_at,
            title=doc.original_filename,
            description=f"Category: {doc.category}" if doc.category else None,
            source_id=doc.id,
            source_url_hint=f"/documents/{doc.id}",
        ))

    # Knowledge-superseded events — chunks belonging to this asset's
    # documents whose valid_to was set (Phase 6 Feature 1). Only include
    # chunks that actually got superseded, not every chunk.
    superseded_query = (
        select(Chunk, Document.original_filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.asset_id == asset_id, Chunk.valid_to.isnot(None))
    )
    if start_date:
        superseded_query = superseded_query.where(Chunk.valid_to >= start_date)
    if end_date:
        superseded_query = superseded_query.where(Chunk.valid_to <= end_date)
    superseded_rows = (await db.execute(superseded_query)).all()

    for chunk, doc_title in superseded_rows:
        events.append(TimelineEvent(
            event_type="knowledge_superseded",
            occurred_at=chunk.valid_to,
            title=f"Content from '{doc_title}' was superseded",
            description=chunk.text[:200],
            source_id=chunk.id,
            source_url_hint=f"/documents/{chunk.document_id}#chunk-{chunk.id}",
        ))

    events.sort(key=lambda e: e.occurred_at)
    return asset, events


async def get_asset_state_at(
    db: AsyncSession,
    asset_id: str,
    as_of: datetime,
) -> Optional[tuple[Asset, list[ReplayChunkState], list[ReplayIncidentState], int]]:
    """
    Reconstructs which chunks were valid, which incidents had occurred,
    and how many documents existed, as of `as_of`. See
    schemas/timeline.py::AssetStateSnapshot for the scope note on what
    this does NOT replay (gap/risk/disagreement score history).
    """
    asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = asset_result.scalar_one_or_none()
    if asset is None:
        return None

    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    valid_chunks_query = (
        select(Chunk, Document.original_filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Document.asset_id == asset_id,
            Chunk.valid_from <= as_of,
            or_(Chunk.valid_to.is_(None), Chunk.valid_to > as_of),
        )
    )
    valid_rows = (await db.execute(valid_chunks_query)).all()
    valid_chunks = [
        ReplayChunkState(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=doc_title,
            content_excerpt=chunk.text[:200],
            trust_score=chunk.trust_score,
        )
        for chunk, doc_title in valid_rows
    ]

    incidents_query = (
        select(Incident)
        .where(Incident.asset_id == asset_id, Incident.occurred_at <= as_of)
        .order_by(Incident.occurred_at.desc())
    )
    incidents = (await db.execute(incidents_query)).scalars().all()
    incident_states = [
        ReplayIncidentState(
            incident_id=inc.id,
            title=inc.title,
            severity=inc.severity.value if hasattr(inc.severity, "value") else str(inc.severity),
            occurred_at=inc.occurred_at,
        )
        for inc in incidents
    ]

    from sqlalchemy import func as sa_func
    doc_count_result = await db.execute(
        select(sa_func.count(Document.id)).where(Document.asset_id == asset_id, Document.created_at <= as_of)
    )
    documents_existing_to_date = doc_count_result.scalar_one()

    return asset, valid_chunks, incident_states, documents_existing_to_date
