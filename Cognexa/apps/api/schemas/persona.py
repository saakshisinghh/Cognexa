"""
apps/api/schemas/persona.py

Phase 6 — AI Shadow Engineer request/response models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CaptureEntryRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=10000)
    asset_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class ExpertKnowledgeEntrySummary(BaseModel):
    id: str
    author_user_id: str
    asset_id: Optional[str] = None
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EntryListResponse(BaseModel):
    entries: list[ExpertKnowledgeEntrySummary]
    total: int


class ExpertPersonaSummary(BaseModel):
    user_id: str
    full_name: str
    entry_count: int


class ExpertPersonaListResponse(BaseModel):
    experts: list[ExpertPersonaSummary]
