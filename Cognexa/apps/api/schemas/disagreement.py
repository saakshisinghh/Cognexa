"""
apps/api/schemas/disagreement.py

Phase 6 — Expert Disagreement Detection request/response models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DisagreementSummary(BaseModel):
    id: str
    asset_id: str
    asset_name: Optional[str] = None
    topic: str
    document_a_id: str
    document_a_title: str
    document_b_id: str
    document_b_title: str
    occurrence_count: int
    max_severity: str
    sample_excerpt_a: Optional[str] = None
    sample_excerpt_b: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    is_resolved: bool
    resolved_by_user_id: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DisagreementListResponse(BaseModel):
    disagreements: list[DisagreementSummary]
    total: int


class ResolveDisagreementRequest(BaseModel):
    notes: Optional[str] = Field(None, description="How this was resolved — which document is authoritative, what was updated, etc.")


class DisagreementRecomputeTriggerResponse(BaseModel):
    task_id: str
    message: str = "Expert disagreement detection recomputation queued."
