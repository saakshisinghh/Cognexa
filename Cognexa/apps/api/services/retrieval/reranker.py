"""
apps/api/services/retrieval/reranker.py

Stage 2 of the post-fusion pipeline: cross-encoder reranking.

RRF fusion (Step 1) ranks purely on RECIPROCAL RANK across sources — it has
no idea whether a chunk is actually semantically relevant to THIS query, it
only knows it scored well in BM25/vector/graph independently. A cross-encoder
reads (query, chunk) pairs together and produces a much more precise
relevance score, at the cost of being too slow to run over the full corpus —
which is exactly why it runs AFTER fusion has already cut the candidate set
down to ~30 chunks, not before.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 — loaded once at process
startup (module-level singleton), same loading pattern as Phase 1's
embedder.py uses for its Sentence Transformer, so there is no duplicated
"how do we load and cache an ML model" pattern introduced here.
"""

import logging
import time
from functools import lru_cache

from apps.api.schemas.retrieval import RetrievedChunk

logger = logging.getLogger("indus_mind.retrieval.reranker")

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Reranking is skipped (chunks pass through unmodified) if the candidate set
# is already smaller than this — there is nothing meaningful to re-order in
# a 1-2 item list, and it avoids paying model inference cost for nothing.
_MIN_CANDIDATES_TO_RERANK = 2


@lru_cache(maxsize=1)
def _get_reranker_model():
    """
    Lazily loads the cross-encoder model on first use and caches it for the
    lifetime of the process. Using lru_cache(maxsize=1) instead of a bare
    module-level global gives us a clean, testable seam — tests can call
    `_get_reranker_model.cache_clear()` to force a fresh load if ever needed,
    and more importantly, the import of this module does NOT eagerly load
    a ~80MB model at import time (which would slow down every test run and
    every cold start that doesn't end up calling rerank()).
    """
    from sentence_transformers import CrossEncoder

    logger.info("loading_reranker_model model=%s", _MODEL_NAME)
    start = time.monotonic()
    model = CrossEncoder(_MODEL_NAME)
    logger.info(
        "reranker_model_loaded model=%s elapsed_ms=%.1f",
        _MODEL_NAME, (time.monotonic() - start) * 1000,
    )
    return model


def rerank(query: str, chunks: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
    """
    Re-scores the fused candidate list using the cross-encoder and returns
    the top_n chunks sorted by rerank_score descending.

    Each chunk's `.rerank_score` field is populated (see schemas/retrieval.py)
    so downstream stages (trust filtering, confidence engine) and the
    frontend source panel (Step 4) can display/use it without recomputation.

    If the cross-encoder model fails to load or errors during inference,
    this function falls back to the RRF fused_score ordering rather than
    raising — reranking is a quality improvement, not a hard dependency,
    and a copilot answer built from RRF-only ordering is still far better
    than no answer at all. This satisfies the "Graceful Recovery" error
    handling requirement.
    """
    if not chunks:
        return []

    if len(chunks) < _MIN_CANDIDATES_TO_RERANK:
        for chunk in chunks:
            chunk.rerank_score = chunk.fused_score
        return chunks[:top_n]

    try:
        model = _get_reranker_model()
        pairs = [(query, chunk.content) for chunk in chunks]
        start = time.monotonic()
        scores = model.predict(pairs)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
    except Exception as exc:  # noqa: BLE001 — broad on purpose, see docstring
        logger.warning(
            "reranker_failed_falling_back_to_rrf_order query=%r error=%s",
            query, str(exc),
        )
        for chunk in chunks:
            chunk.rerank_score = chunk.fused_score
        ranked = sorted(chunks, key=lambda c: c.fused_score, reverse=True)
        return ranked[:top_n]

    for chunk, score in zip(chunks, scores):
        chunk.rerank_score = float(score)

    ranked = sorted(chunks, key=lambda c: c.rerank_score, reverse=True)

    logger.debug(
        "rerank_complete query=%r candidates=%d elapsed_ms=%s top_n=%d",
        query, len(chunks), elapsed_ms, top_n,
    )

    return ranked[:top_n]
