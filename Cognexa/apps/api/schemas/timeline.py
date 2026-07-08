"""
apps/api/schemas/timeline.py

Phase 6 — Failure Time Machine request/response models.

IMPORTANT SCOPE NOTE: "replay" here means reconstructing which
DOCUMENTS/CHUNKS were valid (using Phase 6 Feature 1's
Chunk.valid_from/valid_to) and which INCIDENTS had occurred as of a
given past timestamp — i.e. replaying the raw factual record. It does
NOT replay historical GapScore/risk_score/disagreement values, because
those (AssetKnowledgeGap, AssetKnowledgeLossRisk, AssetExpertDisagreement)
only store their latest computed snapshot, not a history of past values.
Adding that would require a separate time-series table per metric —
a real but separate feature, not silently included here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TimelineEvent(BaseModel):
    event_type: str  # "incident" | "document" | "work_order" | "inspection" | "knowledge_superseded"
    occurred_at: datetime
    title: str
    description: Optional[str] = None
    severity: Optional[str] = None  # populated for event_type="incident"
    source_id: str  # incident.id or document.id or chunk.id, depending on event_type
    source_url_hint: Optional[str] = None  # e.g. "/documents/{id}" — frontend builds the actual link

    model_config = ConfigDict(from_attributes=True)


class AssetTimelineResponse(BaseModel):
    asset_id: str
    asset_name: str
    events: list[TimelineEvent]
    total: int


class ReplayChunkState(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    content_excerpt: str
    trust_score: float
    was_valid_at_query_time: bool = True  # always True for items in the returned list — see services/timeline.py


class ReplayIncidentState(BaseModel):
    incident_id: str
    title: str
    severity: str
    occurred_at: datetime


class AssetStateSnapshot(BaseModel):
    asset_id: str
    asset_name: str
    as_of: datetime
    valid_chunks: list[ReplayChunkState]
    incidents_to_date: list[ReplayIncidentState]
    documents_existing_to_date: int
    note: str = (
        "This reflects which documents/chunks were valid and which incidents had "
        "occurred as of `as_of`. GapScore, knowledge-loss risk, and disagreement "
        "metrics are not historized and always reflect their latest computed value, "
        "not the value as of this timestamp."
    )
