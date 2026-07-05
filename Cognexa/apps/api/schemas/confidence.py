"""
apps/api/schemas/confidence.py

Schemas for the confidence engine and conflict detector outputs.
Kept separate from schemas/retrieval.py because these represent a
DIFFERENT concern: retrieval.py describes "what chunks did we find",
this file describes "how much should the user trust the answer built
from those chunks". Step 3's copilot router composes both.
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConfidenceFactors(BaseModel):
    """
    The individual signals that fed into the final confidence score —
    surfaced to the frontend (Step 4) so the confidence badge can show
    an explanation on hover, per your spec: "Return HIGH/MEDIUM/LOW with
    explanation."
    """
    supporting_document_count: int
    avg_retrieval_score: float = Field(ge=0.0, le=1.0)
    graph_consistency_score: float = Field(ge=0.0, le=1.0)
    citation_count: int
    avg_trust_score: float = Field(ge=0.0, le=1.0)
    has_conflict: bool
    conflict_penalty_applied: float = Field(ge=0.0, le=1.0)


class ConfidenceResult(BaseModel):
    level: ConfidenceLevel
    raw_score: float = Field(ge=0.0, le=1.0)
    factors: ConfidenceFactors
    explanation: str  # human-readable, e.g. "High confidence: 6 supporting
                       # documents from 3 independent sources, no conflicts detected."


class ConflictSeverity(str, Enum):
    MINOR = "minor"       # different phrasing, same underlying fact
    MODERATE = "moderate" # numeric values differ but same category
    MAJOR = "major"       # direct contradiction (e.g. negation detected)


class ConflictFlag(BaseModel):
    """
    A detected disagreement between two retrieved chunks on the same topic.
    """
    topic: str  # e.g. "lubrication_interval", "operating_pressure_limit"
    severity: ConflictSeverity
    chunk_a_id: UUID
    chunk_a_excerpt: str
    chunk_a_document_title: str
    chunk_b_id: UUID
    chunk_b_excerpt: str
    chunk_b_document_title: str
    confidence: float = Field(ge=0.0, le=1.0)  # how confident the detector is
                                                 # that this IS a real conflict
