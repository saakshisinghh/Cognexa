"""
apps/api/services/retrieval/asset_tag_detector.py

Detects industrial asset tag patterns inside a free-text query so the
graph retrieval path knows which assets to expand from in Neo4j.

This is a regex-based detector, not an NLP/spaCy call — it is intentionally
fast and synchronous because it sits on the hot path of every copilot
request and must add near-zero latency. The existing spaCy NER pipeline
(services/extractor.py from Phase 1) is NOT touched or reused here; that
pipeline is built for full-document entity extraction at ingestion time,
not for sub-millisecond query-time tag spotting.

Patterns cover the common industrial tag-numbering conventions already
used elsewhere in the system (see Phase 1 entity extraction regexes):
    Pumps              P-1045, P-101A
    Compressors        K-201, K-2010B
    Vessels             V-301, V-30
    Valves              FV-101, PV-220 (control valve prefixes)
    Instruments         FT-101, TIC-220, LIC-310, PIC-450
    Heat exchangers     E-101, HX-201
"""

import re

# Compiled once at import time — this module is imported once per worker process.
_ASSET_TAG_PATTERN = re.compile(
    r"""
    \b
    (?:
        [PKVE]            # single-letter prefixes: Pump, Compressor (K), Vessel, Exchanger
        |FV|PV|TV|LV       # control valve prefixes
        |FT|TIC|LIC|PIC|TT|PT|LT   # instrument prefixes
        |HX
    )
    -
    \d{2,5}
    [A-Z]?                 # optional suffix letter, e.g. P-1045A
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)


def detect_asset_tags(query: str) -> list[str]:
    """
    Extracts and normalizes asset tag mentions from a query string.

    Example:
        >>> detect_asset_tags("What caused the seal failure on p-1045 last year?")
        ['P-1045']

        >>> detect_asset_tags("Compare K-201 and k-205 vibration trends")
        ['K-201', 'K-205']

    Returns an empty list if no tags are detected — callers (graph_retriever)
    must handle this gracefully by skipping graph expansion rather than
    erroring, since most copilot queries do not mention a specific asset.
    """
    if not query or not query.strip():
        return []

    matches = _ASSET_TAG_PATTERN.findall(query)
    # findall with a non-capturing-only-at-top-level pattern returns full matches
    # via finditer instead, since findall behavior with VERBOSE + alternation
    # at top level returns the whole match (no groups captured) — verified below.
    raw_matches = [m.group(0) for m in _ASSET_TAG_PATTERN.finditer(query)]

    normalized = []
    seen = set()
    for tag in raw_matches:
        upper = tag.upper()
        if upper not in seen:
            seen.add(upper)
            normalized.append(upper)

    return normalized
