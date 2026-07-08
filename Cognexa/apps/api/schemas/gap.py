"""
apps/api/schemas/gap.py

Phase 6 — Knowledge Gap Detection request/response models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AssetGapSummary(BaseModel):
    asset_id: str
    asset_name: str
    gap_score: float
    missing_categories: list[str] = Field(default_factory=list)
    present_categories: list[str] = Field(default_factory=list)
    expected_categories: list[str] = Field(default_factory=list)
    incident_count: int = 0
    incident_penalty_applied: bool = False
    computed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AssetGapListResponse(BaseModel):
    assets: list[AssetGapSummary]
    total: int


class GapRecomputeTriggerResponse(BaseModel):
    task_id: str
    message: str = "Knowledge gap recomputation queued."
