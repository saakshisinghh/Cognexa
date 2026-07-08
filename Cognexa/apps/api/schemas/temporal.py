"""
apps/api/schemas/temporal.py

Phase 6 — Temporal Knowledge Intelligence request/response models.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ChunkTemporalInfo(BaseModel):
    chunk_id: str
    document_id: str
    trust_score: float
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    superseded_by_chunk_id: Optional[str] = None
    decay_computed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SupersedeChunkRequest(BaseModel):
    superseded_by_chunk_id: str = Field(..., description="ID of the chunk that replaces this one")


class StaleDocumentSummary(BaseModel):
    document_id: str
    original_filename: str
    category: Optional[str] = None
    is_stale: bool
    stale_flagged_at: Optional[datetime] = None
    stale_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StaleDocumentListResponse(BaseModel):
    documents: list[StaleDocumentSummary]
    total: int


class RecomputeTriggerResponse(BaseModel):
    task_id: str
    task_name: str
    message: str = "Recomputation task queued."
