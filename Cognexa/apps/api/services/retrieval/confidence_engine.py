"""
apps/api/services/retrieval/confidence_engine.py

Final stage of the post-fusion pipeline: computes a HIGH/MEDIUM/LOW
confidence level with a human-readable explanation, using exactly the six
signals your spec requires:
    1. Number of supporting documents
    2. Retrieval score (avg rerank/fused score of final candidates)
    3. Graph consistency (whether graph-path results agree with
       BM25/vector-path results, i.e. did the graph corroborate or
       contradict the rest of the evidence)
    4. Citation count (final number of distinct chunks used in the answer)
    5. Trust score (avg trust_score of final candidates)
    6. Conflict presence (from conflict_detector.py — reduces confidence)

This module is pure computation — it does not call the LLM, does not
touch the database, and has no I/O, which makes it fully unit-testable
without mocks (see tests/unit/retrieval/test_confidence_engine.py).
"""

import logging

from apps.api.schemas.retrieval import RetrievedChunk
from apps.api.schemas.confidence import (
    ConfidenceFactors,
    ConfidenceLevel,
    ConfidenceResult,
    ConflictFlag,
)

logger = logging.getLogger("indus_mind.retrieval.confidence_engine")

# Thresholds on the final weighted raw_score (0.0-1.0) that determine the
# bucketed confidence level shown to the user.
_HIGH_THRESHOLD = 0.70
_MEDIUM_THRESHOLD = 0.40

# Per-conflict confidence penalty, capped so multiple conflicts can't drive
# confidence below zero — diminishing penalty, not a cliff.
_CONFLICT_PENALTY_PER_FLAG = 0.15
_MAX_CONFLICT_PENALTY = 0.40

# Weighting of each factor in the final raw_score. Sums to 1.0.
_WEIGHT_DOCUMENT_COUNT = 0.20
_WEIGHT_RETRIEVAL_SCORE = 0.30
_WEIGHT_GRAPH_CONSISTENCY = 0.15
_WEIGHT_CITATION_COUNT = 0.15
_WEIGHT_TRUST_SCORE = 0.20

# A query is considered to have "enough" supporting documents at this count
# for the document-count factor to max out (normalizes count -> 0..1).
_DOCUMENT_COUNT_SATURATION = 5
_CITATION_COUNT_SATURATION = 5


def compute_confidence(
    final_chunks: list[RetrievedChunk],
    conflicts: list[ConflictFlag],
    graph_chunk_count: int,
    graph_corroborates: bool = True,
) -> ConfidenceResult:
    """
    Args:
        final_chunks: the fully-processed chunk list AFTER reranking, trust
                      filtering, and temporal boosting — i.e. exactly what
                      will be assembled into the LLM context in Step 3.
        conflicts: output of conflict_detector.detect_conflicts() on this
                   same final_chunks list.
        graph_chunk_count: how many of final_chunks came from the graph
                           retrieval path (source_ranks contains "graph").
        graph_corroborates: True if graph-path chunks support the same
                            conclusion as BM25/vector chunks (no conflicts
                            involving a graph-sourced chunk); False if a
                            conflict specifically involves graph evidence
                            contradicting document evidence. Computed by
                            the caller (Step 3) since it requires knowing
                            which side of a conflict the graph chunk is on.

    Returns:
        ConfidenceResult with level, raw_score, factors, and a one-sentence
        explanation suitable for direct frontend display.
    """
    if not final_chunks:
        return _zero_confidence_result(conflicts)

    distinct_documents = {c.document_id for c in final_chunks}
    supporting_document_count = len(distinct_documents)

    scores = [
        (c.rerank_score if c.rerank_score is not None else c.fused_score)
        for c in final_chunks
    ]
    avg_retrieval_score = _normalize_score(sum(scores) / len(scores))

    graph_consistency_score = 1.0 if graph_corroborates else 0.3
    if graph_chunk_count == 0:
        # No graph evidence either way -> neutral, not penalized for absence.
        graph_consistency_score = 0.6

    citation_count = len(final_chunks)

    avg_trust_score = sum(c.trust_score for c in final_chunks) / len(final_chunks)

    has_conflict = len(conflicts) > 0
    conflict_penalty = min(
        _MAX_CONFLICT_PENALTY, len(conflicts) * _CONFLICT_PENALTY_PER_FLAG
    )

    raw_score = (
        _WEIGHT_DOCUMENT_COUNT * _normalize_count(supporting_document_count, _DOCUMENT_COUNT_SATURATION)
        + _WEIGHT_RETRIEVAL_SCORE * avg_retrieval_score
        + _WEIGHT_GRAPH_CONSISTENCY * graph_consistency_score
        + _WEIGHT_CITATION_COUNT * _normalize_count(citation_count, _CITATION_COUNT_SATURATION)
        + _WEIGHT_TRUST_SCORE * avg_trust_score
    )
    raw_score = max(0.0, raw_score - conflict_penalty)
    raw_score = round(min(1.0, raw_score), 4)

    level = _bucket_score(raw_score)

    factors = ConfidenceFactors(
        supporting_document_count=supporting_document_count,
        avg_retrieval_score=round(avg_retrieval_score, 4),
        graph_consistency_score=round(graph_consistency_score, 4),
        citation_count=citation_count,
        avg_trust_score=round(avg_trust_score, 4),
        has_conflict=has_conflict,
        conflict_penalty_applied=round(conflict_penalty, 4),
    )

    explanation = _build_explanation(level, factors)

    logger.debug(
        "confidence_computed level=%s raw_score=%.3f docs=%d citations=%d conflicts=%d",
        level.value, raw_score, supporting_document_count, citation_count, len(conflicts),
    )

    return ConfidenceResult(
        level=level, raw_score=raw_score, factors=factors, explanation=explanation,
    )


def _normalize_score(score: float) -> float:
    """
    Rerank/fused scores aren't naturally bounded to [0,1] in the same way
    across sources (cross-encoder logits can be negative or >1). Clip into
    a usable range for confidence weighting without distorting comparisons
    within this single request.
    """
    return max(0.0, min(1.0, score))


def _normalize_count(count: int, saturation: int) -> float:
    return min(1.0, count / saturation)


def _bucket_score(raw_score: float) -> ConfidenceLevel:
    if raw_score >= _HIGH_THRESHOLD:
        return ConfidenceLevel.HIGH
    if raw_score >= _MEDIUM_THRESHOLD:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def _build_explanation(level: ConfidenceLevel, factors: ConfidenceFactors) -> str:
    doc_word = "document" if factors.supporting_document_count == 1 else "documents"

    base = (
        f"{level.value.capitalize()} confidence: {factors.supporting_document_count} "
        f"supporting {doc_word}, {factors.citation_count} citations used"
    )

    if factors.has_conflict:
        base += f", but {_conflict_phrase(factors.conflict_penalty_applied)} detected"
    else:
        base += ", no conflicts detected"

    if factors.avg_trust_score < 0.5:
        base += ". Source material includes documents flagged as lower trust"

    return base + "."


def _conflict_phrase(penalty: float) -> str:
    if penalty >= _MAX_CONFLICT_PENALTY:
        return "multiple source conflicts"
    return "a source conflict"


def _zero_confidence_result(conflicts: list[ConflictFlag]) -> ConfidenceResult:
    factors = ConfidenceFactors(
        supporting_document_count=0,
        avg_retrieval_score=0.0,
        graph_consistency_score=0.0,
        citation_count=0,
        avg_trust_score=0.0,
        has_conflict=len(conflicts) > 0,
        conflict_penalty_applied=0.0,
    )
    return ConfidenceResult(
        level=ConfidenceLevel.LOW,
        raw_score=0.0,
        factors=factors,
        explanation="Low confidence: no supporting documents were found for this query.",
    )
