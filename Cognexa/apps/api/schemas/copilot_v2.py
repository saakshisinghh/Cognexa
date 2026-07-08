"""
apps/api/schemas/copilot_v2.py

FIX: The existing schemas/copilot.py file contained copilot_v2 content but was
named copilot.py. The router and service both import from
`apps.api.schemas.copilot_v2` which caused ModuleNotFoundError at startup.

ACTION REQUIRED: Rename apps/api/schemas/copilot.py → apps/api/schemas/copilot_v2.py
(or create this as a new file alongside the original copilot.py if that file
has Phase 1 schemas in it).

This file IS apps/api/schemas/copilot_v2.py — place it at that exact path.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.schemas.confidence import ConfidenceLevel, ConflictFlag


# ── Requests ──────────────────────────────────────────────────────────────

class CopilotV2ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[UUID] = None
    plant_id: Optional[str] = None          # FIX: str not UUID — plant table doesn't exist
    document_type: Optional[str] = None
    asset_id: Optional[str] = None          # FIX: str not UUID — Asset PK is String
    stream: bool = True
    # Phase 6: AI Shadow Engineer — when set, retrieval also pulls this
    # expert's captured knowledge (services/persona.py::get_persona_chunks)
    # alongside normal document retrieval. Optional, defaults to None —
    # existing callers that don't send this field get identical behavior
    # to before this field existed.
    persona_user_id: Optional[str] = None


class PinAssetRequest(BaseModel):
    asset_id: Optional[str] = None          # FIX: str not UUID
    asset_tag: Optional[str] = None


class FeedbackRequest(BaseModel):
    query_id: UUID
    feedback: str = Field(..., pattern="^(positive|negative)$")


# ── Responses ─────────────────────────────────────────────────────────────

class CitationItem(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    page_number: Optional[int] = None
    excerpt: str
    sources: list[str] = Field(default_factory=list)
    trust_score: float


class CopilotV2ChatResponse(BaseModel):
    query_id: UUID
    session_id: str                         # FIX: str — ConversationSession PK is String
    answer: str
    citations: list[CitationItem]
    confidence_level: ConfidenceLevel
    confidence_score: float
    confidence_explanation: str
    conflicts: list[ConflictFlag] = Field(default_factory=list)
    has_conflict: bool
    elapsed_ms: float


class SessionSummary(BaseModel):
    session_id: UUID
    title: Optional[str]
    message_count: int
    pinned_asset_tag: Optional[str]
    last_active_at: Optional[str]
    is_archived: bool


class SessionDetailResponse(BaseModel):
    session: SessionSummary
    recent_messages: list[dict]