"""
apps/api/schemas/loss.py

Phase 6 — Knowledge Loss Prediction request/response models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AssetOwnerSummary(BaseModel):
    user_id: str
    full_name: str
    document_count: int
    incident_count: int
    ownership_score: float
    is_primary_owner: bool
    last_activity_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AssetRiskSummary(BaseModel):
    asset_id: str
    asset_name: str
    primary_owner_user_id: Optional[str] = None
    primary_owner_name: Optional[str] = None
    concentration_score: float
    contributor_count: int
    retirement_boost_applied: bool
    risk_score: float
    risk_level: str
    mitigation_recommendation: Optional[str] = None
    computed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AssetRiskListResponse(BaseModel):
    assets: list[AssetRiskSummary]
    total: int


class AssetOwnersResponse(BaseModel):
    asset_id: str
    owners: list[AssetOwnerSummary]


class SetRetirementFlagRequest(BaseModel):
    is_retirement_risk: bool
    notes: Optional[str] = Field(None, description="Optional HR context — visible only to admins/engineers")


class LossRecomputeTriggerResponse(BaseModel):
    task_id: str
    message: str = "Knowledge loss risk recomputation queued."
