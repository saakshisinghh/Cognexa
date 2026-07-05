"""
apps/api/services/context_assembler.py

Converts the final ranked chunk list from run_triple_retrieval() into:
    1. A formatted context string ready for injection into the LLM prompt
    2. A list of CitationItem objects for the frontend citation panel

This is a pure transformation — no I/O, no LLM calls, no DB access.
Kept as a separate service (not inlined into copilot_v2.py) because:
    a) It has clear independent testability
    b) The citation mapping logic is non-trivial enough to warrant isolation
    c) prompt_engine.py needs the context string but not the CitationItem list,
       while the copilot router needs both — separating the two avoids
       passing unnecessary data through service layers
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from apps.api.schemas.retrieval import RetrievedChunk
from apps.api.schemas.copilot_v2 import CitationItem

_MAX_CHUNK_CHARS = 800    # maximum characters taken from a single chunk for context
_MAX_CONTEXT_CHARS = 12_000  # total context string cap (well within Claude's 200K window;
                              # kept small so the prompt + system text + response fit comfortably)
_CITATION_EXCERPT_CHARS = 300  # characters kept in citation preview panel


def assemble_context(
    chunks: list[RetrievedChunk],
) -> tuple[str, list[CitationItem]]:
    """
    Builds the context string and citation list from the final ranked chunks.

    Returns:
        (context_str, citations)

        context_str: formatted multi-source context block, with a
            [SOURCE:{index}] marker before each chunk so the LLM can
            reference specific sources in its answer. The index matches
            the citation list position so the frontend can link them.

        citations: list of CitationItem in the same order as the context
            markers — index 1 in context_str maps to citations[0].
    """
    if not chunks:
        return "", []

    context_parts: list[str] = []
    citations: list[CitationItem] = []
    total_chars = 0

    for idx, chunk in enumerate(chunks, start=1):
        if total_chars >= _MAX_CONTEXT_CHARS:
            break

        chunk_text = chunk.content[:_MAX_CHUNK_CHARS]
        remaining = _MAX_CONTEXT_CHARS - total_chars
        if len(chunk_text) > remaining:
            chunk_text = chunk_text[:remaining]

        source_tag = f"[SOURCE:{idx}]"
        block = (
            f"{source_tag}\n"
            f"Document: {chunk.document_title}"
            + (f" | Page {chunk.page_number}" if chunk.page_number else "")
            + (f" | Type: {chunk.chunk_type}" if chunk.chunk_type else "")
            + f"\nTrust: {chunk.trust_score:.2f}\n"
            f"{chunk_text}\n"
        )
        context_parts.append(block)
        total_chars += len(block)

        active_sources = list(chunk.source_ranks.keys())

        citations.append(CitationItem(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_title=chunk.document_title,
            page_number=chunk.page_number,
            excerpt=chunk.content[:_CITATION_EXCERPT_CHARS],
            sources=active_sources,
            trust_score=round(chunk.trust_score, 3),
        ))

    context_str = "\n---\n".join(context_parts)
    return context_str, citations
