"""
Chunker Service — Recursive text chunking with overlap and metadata.
"""
from __future__ import annotations
import re
import logging
from typing import List
from dataclasses import dataclass, field

from apps.api.config import settings

logger = logging.getLogger(__name__)

SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    page_number: int | None
    token_count: int
    metadata: dict = field(default_factory=dict)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def _split_on_separator(text: str, separator: str) -> list[str]:
    if separator:
        parts = text.split(separator)
    else:
        parts = list(text)
    return [p for p in parts if p.strip()]


def _merge_splits(splits: list[str], chunk_size: int, overlap: int, separator: str) -> list[str]:
    """Merge small splits up to chunk_size tokens, with overlap."""
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for part in splits:
        part_len = _estimate_tokens(part)
        if current_len + part_len > chunk_size and current_parts:
            # Emit current chunk
            chunks.append(separator.join(current_parts))
            # Apply overlap: keep tail of current_parts
            overlap_tokens = 0
            overlap_parts: list[str] = []
            for p in reversed(current_parts):
                pt = _estimate_tokens(p)
                if overlap_tokens + pt <= overlap:
                    overlap_parts.insert(0, p)
                    overlap_tokens += pt
                else:
                    break
            current_parts = overlap_parts
            current_len = overlap_tokens

        current_parts.append(part)
        current_len += part_len

    if current_parts:
        chunks.append(separator.join(current_parts))

    return chunks


def _recursive_split(text: str, chunk_size: int, overlap: int, separators: list[str]) -> list[str]:
    """Recursively split text using the best separator."""
    if _estimate_tokens(text) <= chunk_size:
        return [text]

    separator = ""
    remaining_separators = separators[:]

    while remaining_separators:
        sep = remaining_separators.pop(0)
        if sep == "" or sep in text:
            separator = sep
            break

    splits = _split_on_separator(text, separator)
    final_chunks: list[str] = []

    for split in splits:
        if _estimate_tokens(split) <= chunk_size:
            final_chunks.append(split)
        else:
            sub_chunks = _recursive_split(split, chunk_size, overlap, separators[:])
            final_chunks.extend(sub_chunks)

    return _merge_splits(final_chunks, chunk_size, overlap, separator)


def split_text(
    text: str,
    document_id: str,
    source: str = "",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[TextChunk]:
    """
    Split text into chunks with metadata.
    Returns list of TextChunk objects ready for embedding.
    """
    if not text or not text.strip():
        return []

    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    # Detect page boundaries (form feeds or "Page N" markers)
    page_texts: list[tuple[int, str]] = []
    raw_pages = re.split(r"\f|(?:^|\n)(?:page\s+\d+\s*\n)", text, flags=re.IGNORECASE)
    for idx, page_text in enumerate(raw_pages, start=1):
        if page_text.strip():
            page_texts.append((idx, page_text))

    chunks: list[TextChunk] = []
    chunk_index = 0

    for page_num, page_text in page_texts:
        raw_chunks = _recursive_split(
            page_text.strip(), chunk_size, chunk_overlap, SEPARATORS[:]
        )
        for raw in raw_chunks:
            if not raw.strip():
                continue
            chunks.append(
                TextChunk(
                    text=raw.strip(),
                    chunk_index=chunk_index,
                    page_number=page_num,
                    token_count=_estimate_tokens(raw),
                    metadata={
                        "document_id": document_id,
                        "source": source,
                        "page_number": page_num,
                        "chunk_index": chunk_index,
                    },
                )
            )
            chunk_index += 1

    logger.info(
        f"Chunked document {document_id}: {len(chunks)} chunks "
        f"(chunk_size={chunk_size}, overlap={chunk_overlap})"
    )
    return chunks
