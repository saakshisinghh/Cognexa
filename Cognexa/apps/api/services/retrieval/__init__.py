"""
Phase 4 — Advanced Retrieval Pipeline

This package implements the triple-retrieval layer (BM25 + Vector + Graph)
and fuses results with Reciprocal Rank Fusion (RRF).

It is intentionally isolated from services/rag.py (the Phase 1 basic RAG
pipeline). Phase 4's copilot router will call into this package instead of
services/rag.py's retrieval logic, while still reusing rag.py's existing
Weaviate client, embedder, and Claude API call wrapper where appropriate.

Public API:
    run_triple_retrieval(query, top_k, filters) -> FusedRetrievalResult
"""

from apps.api.services.retrieval.bm25_retriever import bm25_retrieve
from apps.api.services.retrieval.vector_retriever import vector_retrieve
from apps.api.services.retrieval.graph_retriever import graph_retrieve
from apps.api.services.retrieval.rrf_fusion import reciprocal_rank_fusion
from apps.api.services.retrieval.asset_tag_detector import detect_asset_tags
from apps.api.services.retrieval.reranker import rerank
from apps.api.services.retrieval.trust_filter import apply_trust_filter
from apps.api.services.retrieval.temporal_boost import apply_temporal_boost
from apps.api.services.retrieval.conflict_detector import detect_conflicts
from apps.api.services.retrieval.confidence_engine import compute_confidence

__all__ = [
    "bm25_retrieve",
    "vector_retrieve",
    "graph_retrieve",
    "reciprocal_rank_fusion",
    "detect_asset_tags",
    "rerank",
    "apply_trust_filter",
    "apply_temporal_boost",
    "detect_conflicts",
    "compute_confidence",
    "run_triple_retrieval",
]

import asyncio
import logging
import time
from typing import Optional

from apps.api.schemas.retrieval import (
    RetrievalFilters,
    RetrievedChunk,
    FusedRetrievalResult,
    RetrievalSourceStats,
)

logger = logging.getLogger("indus_mind.retrieval")


async def run_triple_retrieval(
    query: str,
    top_k: int = 30,
    top_k_final: int = 8,
    filters: Optional[RetrievalFilters] = None,
) -> FusedRetrievalResult:
    """
    Orchestrates the full Phase 4 retrieval pipeline:

        1. Triple retrieval (BM25 + vector + graph) in parallel  [Step 1]
        2. Reciprocal Rank Fusion                                 [Step 1]
        3. Cross-encoder reranking                                [Step 2]
        4. Trust score filtering                                  [Step 2]
        5. Temporal preference boosting                           [Step 2]
        6. Conflict detection                                     [Step 2]
        7. Confidence scoring                                     [Step 2]

    This is the single entry point Step 3's copilot router will call —
    by the time this function returns, `result.chunks` is the final,
    ready-for-LLM-context-assembly candidate set (already reranked,
    filtered, and boosted), and `result.confidence` / `result.conflicts`
    are ready for direct frontend display.

    Args:
        query: raw user query text
        top_k: number of candidates to request from EACH retrieval path
               before fusion (kept generous — fusion + reranking will
               narrow this down)
        top_k_final: number of chunks to keep after reranking — this is
                     the actual context size that reaches the LLM
        filters: optional filters (document_type, asset_id, date_range, plant_id)

    Returns:
        FusedRetrievalResult with the fully-processed chunk list, confidence,
        and any detected conflicts.
    """
    filters = filters or RetrievalFilters()
    start = time.monotonic()

    # Detect asset tags mentioned in the query (e.g. "P-1045") — needed by
    # the graph retrieval path to know which assets to expand from.
    detected_tags = detect_asset_tags(query)

    # Run all three retrieval paths concurrently. Each coroutine is wrapped
    # in `_safe_call` so one path's exception cannot crash retrieval as a
    # whole — it returns an empty result with an error flag instead.
    bm25_task = _safe_call("bm25", bm25_retrieve(query=query, top_k=top_k, filters=filters))
    vector_task = _safe_call("vector", vector_retrieve(query=query, top_k=top_k, filters=filters))
    graph_task = _safe_call(
        "graph",
        graph_retrieve(asset_tags=detected_tags, top_k=top_k, filters=filters),
    )

    bm25_result, vector_result, graph_result = await asyncio.gather(
        bm25_task, vector_task, graph_task
    )

    source_stats = RetrievalSourceStats(
        bm25_count=len(bm25_result.chunks),
        bm25_ok=bm25_result.ok,
        bm25_error=bm25_result.error,
        vector_count=len(vector_result.chunks),
        vector_ok=vector_result.ok,
        vector_error=vector_result.error,
        graph_count=len(graph_result.chunks),
        graph_ok=graph_result.ok,
        graph_error=graph_result.error,
        detected_asset_tags=detected_tags,
    )

    # If ALL THREE paths failed, raise — there's nothing to retrieve from.
    # This is the one case Step 1 surfaces as a hard failure; everything
    # else degrades gracefully (e.g. graph down but BM25+vector still work).
    if not bm25_result.ok and not vector_result.ok and not graph_result.ok:
        logger.error(
            "retrieval_total_failure query=%r bm25_err=%s vector_err=%s graph_err=%s",
            query, bm25_result.error, vector_result.error, graph_result.error,
        )
        raise RetrievalUnavailableError(
            "All retrieval sources (BM25, vector, graph) are currently unavailable."
        )

    fused: list[RetrievedChunk] = reciprocal_rank_fusion(
        result_sets={
            "bm25": bm25_result.chunks,
            "vector": vector_result.chunks,
            "graph": graph_result.chunks,
        },
        k_constant=60,
    )

    # ── Step 2 pipeline stages — run in the exact order specified ──────────
    reranked = rerank(query=query, chunks=fused, top_n=top_k)
    trusted = apply_trust_filter(reranked)
    boosted = apply_temporal_boost(trusted)
    final_chunks = boosted[:top_k_final]

    conflicts = detect_conflicts(final_chunks)

    graph_chunk_ids = {c.chunk_id for c in graph_result.chunks}
    graph_chunk_count = sum(1 for c in final_chunks if c.chunk_id in graph_chunk_ids)
    graph_involved_in_conflict = any(
        flag.chunk_a_id in graph_chunk_ids or flag.chunk_b_id in graph_chunk_ids
        for flag in conflicts
    )
    graph_corroborates = not graph_involved_in_conflict

    confidence = compute_confidence(
        final_chunks=final_chunks,
        conflicts=conflicts,
        graph_chunk_count=graph_chunk_count,
        graph_corroborates=graph_corroborates,
    )
    # ── end Step 2 pipeline stages ──────────────────────────────────────────

    elapsed_ms = round((time.monotonic() - start) * 1000, 1)
    logger.info(
        "triple_retrieval_complete query=%r elapsed_ms=%s bm25=%d vector=%d graph=%d "
        "fused=%d final=%d confidence=%s conflicts=%d",
        query, elapsed_ms, source_stats.bm25_count, source_stats.vector_count,
        source_stats.graph_count, len(fused), len(final_chunks),
        confidence.level.value, len(conflicts),
    )

    return FusedRetrievalResult(
        chunks=final_chunks,
        source_stats=source_stats,
        elapsed_ms=elapsed_ms,
        confidence=confidence,
        conflicts=conflicts,
    )


class RetrievalUnavailableError(Exception):
    """Raised when every retrieval path fails. Caught in copilot router (Step 3)."""
    pass


class _SafeResult:
    __slots__ = ("chunks", "ok", "error")

    def __init__(self, chunks, ok: bool, error: Optional[str]):
        self.chunks = chunks
        self.ok = ok
        self.error = error


async def _safe_call(source_name: str, coro) -> "_SafeResult":
    """
    Wraps a retrieval coroutine so individual source failures degrade
    gracefully instead of crashing asyncio.gather entirely.
    """
    try:
        chunks = await coro
        return _SafeResult(chunks=chunks, ok=True, error=None)
    except Exception as exc:  # noqa: BLE001 — intentionally broad; logged below
        logger.warning("retrieval_source_failed source=%s error=%s", source_name, str(exc))
        return _SafeResult(chunks=[], ok=False, error=str(exc))
