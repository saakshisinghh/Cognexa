"""
apps/api/services/retrieval/conflict_detector.py

Detects disagreement between top-ranked chunks on the same topic, e.g.
two maintenance procedures recommending different lubrication intervals
for the same equipment class. Runs on the final post-rerank/boost
candidate set (small, ~8-10 chunks) — not the raw fusion set — since
running NLI-style comparison pairwise is O(n^2) and we want n to be small
by this point in the pipeline.

Detection approach (lightweight, no separate NLI model — chosen so Phase 4
doesn't need to load a THIRD ML model alongside the embedder and reranker):
    1. Group chunks by topic keyword overlap (lubrication interval,
       inspection frequency, operating pressure/temperature limits —
       the same topic vocabulary used in the roadmap's "Expert
       Disagreement Detection" Phase 6 feature, reused here at copilot-time
       scope rather than asset-wide batch scope).
    2. Within a topic group, extract numeric values + units via regex.
    3. If two chunks in the same topic group report different numeric
       values, OR one contains a negation pattern relative to the other
       ("must not exceed" vs "may exceed"), flag as a conflict.

This is intentionally a precision-over-recall heuristic: it will miss
some subtle conflicts, but it will not flood the user with false-positive
warnings on every query, which would erode trust in the warning itself.
"""

import logging
import re
from itertools import combinations

from apps.api.schemas.retrieval import RetrievedChunk
from apps.api.schemas.confidence import ConflictFlag, ConflictSeverity

logger = logging.getLogger("indus_mind.retrieval.conflict_detector")

# Topic keyword groups — a chunk is assigned to a topic if any of its
# keywords appear in the chunk content (case-insensitive).
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "lubrication_interval": ["lubricat", "grease interval", "oil change interval"],
    "inspection_frequency": ["inspection interval", "inspection frequency", "inspect every"],
    "operating_pressure_limit": ["operating pressure", "max pressure", "pressure limit"],
    "operating_temperature_limit": ["operating temperature", "max temperature", "temperature limit"],
    "maintenance_interval": ["maintenance interval", "service interval", "pm interval"],
}

# Captures a number followed by a unit token, e.g. "3 months", "6-month",
# "150 psi", "200°C". Deliberately simple — precision over completeness.
_VALUE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*-?\s*(month|months|day|days|week|weeks|year|years|psi|bar|°c|°f|celsius|fahrenheit)",
    re.IGNORECASE,
)

_NEGATION_MARKERS = ["must not", "should not", "do not", "shall not", "never exceed"]
_AFFIRMATION_MARKERS = ["may exceed", "can exceed", "up to", "permitted up to"]


def detect_conflicts(chunks: list[RetrievedChunk]) -> list[ConflictFlag]:
    """
    Returns a list of ConflictFlag for every detected contradiction among
    the given chunks. Returns [] if no conflicts found or fewer than 2
    chunks provided — a single chunk cannot conflict with itself.
    """
    if len(chunks) < 2:
        return []

    topic_groups = _group_by_topic(chunks)
    conflicts: list[ConflictFlag] = []

    for topic, members in topic_groups.items():
        if len(members) < 2:
            continue

        for chunk_a, chunk_b in combinations(members, 2):
            # Never flag two chunks from the same source document as
            # conflicting with each other — that's the same document
            # being chunked, not a cross-document disagreement.
            if chunk_a.document_id == chunk_b.document_id:
                continue

            flag = _compare_pair(topic, chunk_a, chunk_b)
            if flag:
                conflicts.append(flag)

    if conflicts:
        logger.info(
            "conflicts_detected count=%d topics=%s",
            len(conflicts), list({c.topic for c in conflicts}),
        )

    return conflicts


def _group_by_topic(chunks: list[RetrievedChunk]) -> dict[str, list[RetrievedChunk]]:
    groups: dict[str, list[RetrievedChunk]] = {topic: [] for topic in _TOPIC_KEYWORDS}

    for chunk in chunks:
        content_lower = chunk.content.lower()
        for topic, keywords in _TOPIC_KEYWORDS.items():
            if any(kw in content_lower for kw in keywords):
                groups[topic].append(chunk)

    return {topic: members for topic, members in groups.items() if members}


def _compare_pair(
    topic: str, chunk_a: RetrievedChunk, chunk_b: RetrievedChunk
) -> ConflictFlag | None:
    values_a = _extract_values(chunk_a.content)
    values_b = _extract_values(chunk_b.content)

    # Case 1: both chunks state a numeric value for this topic, and they differ.
    if values_a and values_b:
        # Compare the first extracted value pair (number, unit) from each.
        num_a, unit_a = values_a[0]
        num_b, unit_b = values_b[0]
        if unit_a.lower() == unit_b.lower() and num_a != num_b:
            return ConflictFlag(
                topic=topic,
                severity=ConflictSeverity.MODERATE,
                chunk_a_id=chunk_a.chunk_id,
                chunk_a_excerpt=_excerpt(chunk_a.content),
                chunk_a_document_title=chunk_a.document_title,
                chunk_b_id=chunk_b.chunk_id,
                chunk_b_excerpt=_excerpt(chunk_b.content),
                chunk_b_document_title=chunk_b.document_title,
                confidence=0.75,
            )

    # Case 2: one chunk uses a negation/restriction marker, the other an
    # affirmation/permission marker on the same topic — a stronger MAJOR
    # signal regardless of whether numeric values were extractable.
    a_negates = any(m in chunk_a.content.lower() for m in _NEGATION_MARKERS)
    b_affirms = any(m in chunk_b.content.lower() for m in _AFFIRMATION_MARKERS)
    b_negates = any(m in chunk_b.content.lower() for m in _NEGATION_MARKERS)
    a_affirms = any(m in chunk_a.content.lower() for m in _AFFIRMATION_MARKERS)

    if (a_negates and b_affirms) or (b_negates and a_affirms):
        return ConflictFlag(
            topic=topic,
            severity=ConflictSeverity.MAJOR,
            chunk_a_id=chunk_a.chunk_id,
            chunk_a_excerpt=_excerpt(chunk_a.content),
            chunk_a_document_title=chunk_a.document_title,
            chunk_b_id=chunk_b.chunk_id,
            chunk_b_excerpt=_excerpt(chunk_b.content),
            chunk_b_document_title=chunk_b.document_title,
            confidence=0.85,
        )

    return None


def _extract_values(content: str) -> list[tuple[float, str]]:
    matches = _VALUE_PATTERN.findall(content)
    return [(float(num), unit) for num, unit in matches]


def _excerpt(content: str, max_length: int = 200) -> str:
    if len(content) <= max_length:
        return content
    return content[:max_length].rsplit(" ", 1)[0] + "..."
