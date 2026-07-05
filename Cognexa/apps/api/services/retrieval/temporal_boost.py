"""
apps/api/services/retrieval/temporal_boost.py

Stage 4 of the post-fusion pipeline: temporal preference scoring.

Unlike trust_filter.py (hard exclusion), this is a SOFT score adjustment:
recent chunks get a multiplicative boost to their rerank_score so that,
all else being equal, a 2024 procedure outranks a 2015 procedure on the
same topic — without excluding the older one outright, since older
documents are often still the only source for historical incident
context (which the RCA-style "what happened in 2019" queries need).

The boost curve is intentionally gentle (max ~1.15x at most recent,
decaying toward 1.0x at the age cutoff) so that a highly-relevant old
document can still outrank a barely-relevant new one — temporal
preference is a tiebreaker signal, not a relevance override.
"""

import logging
from datetime import date
from typing import Optional

from apps.api.schemas.retrieval import RetrievedChunk

logger = logging.getLogger("indus_mind.retrieval.temporal_boost")

# Boost decays linearly from MAX_BOOST at age=0 to 1.0 (no boost) at this age.
_BOOST_DECAY_YEARS = 3.0
_MAX_BOOST = 1.15


def apply_temporal_boost(
    chunks: list[RetrievedChunk],
    reference_date: Optional[date] = None,
) -> list[RetrievedChunk]:
    """
    Multiplies each chunk's rerank_score by a recency boost factor and
    RE-SORTS the list by the boosted score. Mutates rerank_score in place
    (this is intentional — by this stage in the pipeline, rerank_score IS
    the working relevance score that subsequent stages and the final
    context assembly read from; we are not introducing a third parallel
    score field for this).

    Chunks with no document_date (graph-derived synthetic chunks from
    graph_retriever.py, or any chunk where document_date metadata is
    missing) receive boost=1.0 — neither boosted nor penalized, since we
    have no temporal information to act on.

    Returns the same list, re-sorted — does not change list membership,
    only ordering and rerank_score values.
    """
    if not chunks:
        return []

    reference_date = reference_date or date.today()

    for chunk in chunks:
        boost = _compute_boost(chunk.document_date, reference_date)
        base_score = chunk.rerank_score if chunk.rerank_score is not None else chunk.fused_score
        chunk.rerank_score = base_score * boost

    reordered = sorted(chunks, key=lambda c: c.rerank_score, reverse=True)

    logger.debug("temporal_boost_applied chunks=%d reference_date=%s", len(chunks), reference_date)

    return reordered


def _compute_boost(document_date: Optional[date], reference_date: date) -> float:
    if document_date is None:
        return 1.0

    age_years = max(0.0, (reference_date - document_date).days / 365.25)

    if age_years >= _BOOST_DECAY_YEARS:
        return 1.0

    # Linear interpolation: age=0 -> _MAX_BOOST, age=_BOOST_DECAY_YEARS -> 1.0
    fraction_of_decay = age_years / _BOOST_DECAY_YEARS
    return _MAX_BOOST - (fraction_of_decay * (_MAX_BOOST - 1.0))
