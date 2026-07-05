"""
apps/api/schemas/retrieval.py

Pydantic models for the Phase 4 advanced retrieval pipeline.
These are additive — they do not modify or replace any Phase 1 schema
(e.g. schemas/copilot.py from the basic RAG pipeline, if it exists).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RetrievalFilters(BaseModel):
    """Optional filters applied identically across all three retrieval paths."""
    document_type: Optional[str] = None
    asset_id: Optional[UUID] = None
    plant_id: Optional[UUID] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    min_trust_score: float = Field(default=0.0, ge=0.0, le=1.0)


class RetrievalSourceEnum(str, Enum):
    BM25 = "bm25"
    VECTOR = "vector"
    GRAPH = "graph"


class RetrievedChunk(BaseModel):
    """
    A single retrieved chunk, normalized across all three retrieval sources
    so RRF fusion can operate on a uniform shape regardless of where the
    chunk came from.
    """
    chunk_id: UUID
    document_id: UUID
    document_title: str
    content: str
    page_number: Optional[int] = None
    chunk_type: Optional[str] = None
    trust_score: float = 1.0
    document_date: Optional[date] = None
    asset_ids: list[UUID] = Field(default_factory=list)

    # Per-source provenance — which path(s) returned this chunk and at what rank.
    # Populated incrementally as the chunk passes through retrieval -> fusion.
    source_ranks: dict[RetrievalSourceEnum, int] = Field(default_factory=dict)
    source_scores: dict[RetrievalSourceEnum, float] = Field(default_factory=dict)

    # Set during fusion (Step 1) and overwritten during reranking (Step 2)
    fused_score: float = 0.0
    rerank_score: Optional[float] = None

    model_config = ConfigDict(use_enum_values=True)


class RetrievalSourceStats(BaseModel):
    """Per-source diagnostics returned alongside fused results — used for
    confidence scoring (Step 2) and for debugging/observability."""
    bm25_count: int
    bm25_ok: bool
    bm25_error: Optional[str] = None

    vector_count: int
    vector_ok: bool
    vector_error: Optional[str] = None

    graph_count: int
    graph_ok: bool
    graph_error: Optional[str] = None

    detected_asset_tags: list[str] = Field(default_factory=list)


class FusedRetrievalResult(BaseModel):
    """
    Output of run_triple_retrieval().

    `chunks` is populated by Step 1 (raw RRF fusion) and then PROGRESSIVELY
    REFINED in place by Step 2's pipeline stages (reranked, trust-filtered,
    temporally-boosted) — by the time this object is returned to a Step 3
    caller, `chunks` holds the final, ready-for-LLM-context candidate set,
    not the raw fusion output.

    `confidence` and `conflicts` are None only in the (untested-path)
    scenario where a caller invokes raw fusion directly without going
    through the full pipeline; the standard entry point
    `run_triple_retrieval()` always populates them.
    """
    chunks: list[RetrievedChunk]
    source_stats: RetrievalSourceStats
    elapsed_ms: float
    confidence: Optional["ConfidenceResult"] = None
    conflicts: list["ConflictFlag"] = Field(default_factory=list)


# Deferred import + forward-ref rebuild: schemas/confidence.py does not
# import schemas/retrieval.py, so there is no circular import risk — this
# just keeps confidence.py's types out of retrieval.py's top-level import
# list, since retrieval.py is the more foundational, frequently-imported
# module (used by all three retrievers in Step 1) and should not gain a
# hard dependency on confidence-engine-specific types.
from apps.api.schemas.confidence import ConfidenceResult, ConflictFlag  # noqa: E402

FusedRetrievalResult.model_rebuild()
