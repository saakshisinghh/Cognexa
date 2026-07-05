"""
apps/api/services/retrieval/trust_filter.py

Stage 3 of the post-fusion pipeline: trust score filtering.

Excludes chunks whose `trust_score` (a field that ALREADY EXISTS on
document_chunks from Phase 1/2 — versioning and audit work) falls below
threshold, and chunks belonging to documents older than a configurable
max age. This is a hard exclusion, not a scoring adjustment — a chunk
that fails trust filtering is removed entirely and will never reach the
LLM context window, regardless of how well it scored in reranking.

This module does NOT compute trust_score — that field is populated
elsewhere (Phase 1 ingestion default = 1.0; Phase 6's Knowledge Decay
Score will later update it dynamically, per the roadmap's services/decay.py,
which is explicitly out of scope for Phase 4). This module only READS
the existing field and applies a threshold.
"""

import logging
from datetime import date
from typing import Optional

from apps.api.schemas.retrieval import RetrievedChunk

logger = logging.getLogger("indus_mind.retrieval.trust_filter")

DEFAULT_MIN_TRUST_SCORE = 0.3
DEFAULT_MAX_DOCUMENT_AGE_YEARS: Optional[int] = 7  # None disables age filtering


def apply_trust_filter(
    chunks: list[RetrievedChunk],
    min_trust_score: float = DEFAULT_MIN_TRUST_SCORE,
    max_document_age_years: Optional[int] = DEFAULT_MAX_DOCUMENT_AGE_YEARS,
    reference_date: Optional[date] = None,
) -> list[RetrievedChunk]:
    """
    Filters out chunks below the trust threshold or older than the max age.

    Graph-derived synthetic chunks (from graph_retriever.py — incidents,
    failure modes) have document_date=None and trust_score=1.0 by
    construction; they always pass the age check (no date to violate) and
    pass the trust check by default (full trust). This is intentional:
    graph facts come directly from structured incident/failure-mode
    records, not from potentially-stale free text, so a different
    trust model applies to them than to document prose.

    Returns a NEW filtered list — does not mutate the input list in place,
    so callers retain the option to inspect what was excluded if needed
    for logging/debugging (see _log_exclusions below).
    """
    if not chunks:
        return []

    reference_date = reference_date or date.today()
    kept: list[RetrievedChunk] = []
    excluded_low_trust = 0
    excluded_stale = 0

    for chunk in chunks:
        if chunk.trust_score < min_trust_score:
            excluded_low_trust += 1
            continue

        if (
            max_document_age_years is not None
            and chunk.document_date is not None
            and _years_between(chunk.document_date, reference_date) > max_document_age_years
        ):
            excluded_stale += 1
            continue

        kept.append(chunk)

    if excluded_low_trust or excluded_stale:
        logger.debug(
            "trust_filter_applied input=%d kept=%d excluded_low_trust=%d excluded_stale=%d "
            "min_trust_score=%.2f max_age_years=%s",
            len(chunks), len(kept), excluded_low_trust, excluded_stale,
            min_trust_score, max_document_age_years,
        )

    return kept


def _years_between(earlier: date, later: date) -> float:
    """Approximate year difference — sufficient precision for an age threshold."""
    return (later - earlier).days / 365.25
