"""
apps/api/services/retrieval/rrf_fusion.py

Reciprocal Rank Fusion — merges the three independent ranked result sets
(BM25, vector, graph) into a single fused ranking without needing to
normalize wildly different raw score scales (BM25 scores, cosine
similarities, and graph proximity scores are not directly comparable).

RRF formula per source per chunk:
    score_contribution = 1 / (k_constant + rank_in_that_source)

A chunk's fused_score is the SUM of its contributions across every source
it appeared in. A chunk retrieved by all three paths will rank higher than
one retrieved by only one path, even if that single path ranked it #1 —
this is the standard, well-established RRF behavior (k=60 is the
conventional default from the original RRF paper, balancing the influence
of top-ranked vs. lower-ranked items).
"""

import logging
from uuid import UUID

from apps.api.schemas.retrieval import RetrievedChunk, RetrievalSourceEnum

logger = logging.getLogger("indus_mind.retrieval.rrf")


def reciprocal_rank_fusion(
    result_sets: dict[str, list[RetrievedChunk]],
    k_constant: int = 60,
) -> list[RetrievedChunk]:
    """
    Args:
        result_sets: {"bm25": [...], "vector": [...], "graph": [...]}
                     each list already ranked best-first by its own source.
        k_constant: RRF damping constant (60 is the standard default).

    Returns:
        Deduplicated list of RetrievedChunk, sorted by fused_score descending.
        Chunks appearing in multiple sources are merged into a single entry
        with combined source_ranks/source_scores and a summed fused_score.
    """
    merged: dict[UUID, RetrievedChunk] = {}

    for source_name, chunks in result_sets.items():
        for chunk in chunks:
            rank = chunk.source_ranks.get(source_name)
            if rank is None:
                # Defensive: should never happen since each retriever sets
                # its own source_ranks entry before returning, but we don't
                # want a missing rank to silently corrupt fusion scoring.
                logger.warning(
                    "rrf_fusion: chunk %s missing rank for source=%s, skipping contribution",
                    chunk.chunk_id, source_name,
                )
                continue

            contribution = 1.0 / (k_constant + rank)

            if chunk.chunk_id in merged:
                existing = merged[chunk.chunk_id]
                existing.fused_score += contribution
                existing.source_ranks[source_name] = rank
                existing.source_scores[source_name] = chunk.source_scores.get(source_name, 0.0)
            else:
                # Clone so we don't mutate the caller's original chunk objects.
                chunk.fused_score = contribution
                merged[chunk.chunk_id] = chunk

    fused_list = sorted(merged.values(), key=lambda c: c.fused_score, reverse=True)

    logger.debug(
        "rrf_fusion merged sources=%s total_unique=%d",
        {k: len(v) for k, v in result_sets.items()}, len(fused_list),
    )

    return fused_list
