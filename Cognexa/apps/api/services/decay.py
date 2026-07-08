"""
apps/api/services/decay.py

Phase 6 — Temporal Knowledge Intelligence: trust decay calculation.

Pure functions only (no DB session, no I/O) so this module can be called
identically from:
    - services/temporal.py (async, on-demand recompute via API)
    - workers/temporal_tasks.py (sync Celery, nightly batch recompute)

The formula is a deliberately simple, explainable exponential half-life
decay — NOT a learned/ML model. This is a starting heuristic; tune
HALF_LIFE_DAYS_BY_CATEGORY as real usage data comes in. It intentionally
does not try to be clever about document content — only document
category and elapsed time, both of which are already reliably available
(Document.category, Chunk.valid_from) without depending on anything new.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# Half-life in days per Document.category value: how long until a
# chunk's trust_score decays to 50% of its starting value, all else
# equal. Longer half-life = ages more slowly (e.g. reference procedures
# that rarely change). Shorter = ages faster (e.g. incident reports,
# whose operational relevance fades faster than a spec sheet's).
HALF_LIFE_DAYS_BY_CATEGORY: dict[str, int] = {
    "procedure": 730,
    "manual": 730,
    "sop": 730,
    "specification": 1095,
    "compliance": 365,
    "inspection": 365,
    "incident": 545,
    "work_order": 270,
}
DEFAULT_HALF_LIFE_DAYS = 500

# Trust never decays below this floor from age alone — a very old
# document is still worth surfacing at low confidence, not zeroed out.
MIN_TRUST_SCORE = 0.05

# A chunk that has been explicitly superseded (valid_to is set) is
# capped at this ceiling regardless of age — it's known-outdated
# information, not just aging information, so it should rank low even
# if it was superseded yesterday.
SUPERSEDED_TRUST_CEILING = 0.15


def compute_trust_score(
    valid_from: Optional[datetime],
    valid_to: Optional[datetime],
    category: Optional[str],
    now: Optional[datetime] = None,
) -> float:
    """
    Returns a trust score in [MIN_TRUST_SCORE, 1.0].

    valid_from=None is treated as "just created" (score 1.0) rather than
    raising — existing rows created before this Phase 6 migration may not
    have a backfilled valid_from yet.
    """
    now = now or datetime.now(timezone.utc)

    if valid_from is None:
        base_score = 1.0
    else:
        vf = valid_from if valid_from.tzinfo else valid_from.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - vf).total_seconds() / 86400.0)
        half_life = HALF_LIFE_DAYS_BY_CATEGORY.get((category or "").lower(), DEFAULT_HALF_LIFE_DAYS)
        base_score = 0.5 ** (age_days / half_life)

    score = max(MIN_TRUST_SCORE, min(1.0, base_score))

    if valid_to is not None:
        score = min(score, SUPERSEDED_TRUST_CEILING)

    return round(score, 4)


def is_document_stale(chunk_trust_scores: list[float], threshold: float = 0.4) -> bool:
    """
    A document is considered stale when the average trust_score across
    its chunks drops below `threshold`. Documents with no chunks yet
    (still processing) are never considered stale.
    """
    if not chunk_trust_scores:
        return False
    avg = sum(chunk_trust_scores) / len(chunk_trust_scores)
    return avg < threshold
