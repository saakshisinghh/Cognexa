"""
apps/api/services/gap.py

Phase 6 — Knowledge Gap Detection.

Pure scoring functions (no DB/IO) + async, DB-facing functions used by
routers/gap.py. The actual nightly recomputation across all assets lives
in workers/gap_tasks.py (sync Celery) — this module's async functions
are for the on-demand, read-path API calls, plus a shared pure
compute_gap_score() both call.

WEIGHTS AND EXPECTED CATEGORIES ARE A HEURISTIC STARTING POINT.
Asset.asset_type is a free-text field with no existing taxonomy in this
codebase (no enum, no lookup table) — so this deliberately does NOT try
to vary expected documentation by asset type yet. One universal
checklist is applied to every asset. Once a real asset-type taxonomy
exists, EXPECTED_CATEGORY_WEIGHTS can be keyed by asset_type instead of
being a single flat dict — tracked here as a known simplification, not
silently assumed away.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import AssetKnowledgeGap, Asset

# category -> criticality weight. Higher weight = more damaging to the
# score if missing. Sums do not need to add to 1.0 — compute_gap_score
# normalizes against whatever subset actually applies.
EXPECTED_CATEGORY_WEIGHTS: dict[str, float] = {
    "procedure": 1.0,
    "manual": 1.0,
    "compliance": 0.9,
    "inspection": 0.8,
    "specification": 0.7,
}

# Extra penalty added to the base score when an asset has 1+ recorded
# incidents but is missing BOTH "procedure" and "manual" documentation —
# i.e. it has actually failed and still has no documented fix/prevention
# procedure on file. Capped so gap_score never exceeds 1.0.
INCIDENT_WITHOUT_PROCEDURE_PENALTY = 0.15
_PROCEDURE_CATEGORIES = {"procedure", "manual"}


def compute_gap_score(
    present_categories: set[str],
    incident_count: int,
    category_weights: Optional[dict[str, float]] = None,
) -> tuple[float, list[str], list[str], bool]:
    """
    Returns (gap_score, missing_categories, expected_categories, incident_penalty_applied).

    gap_score is in [0.0, 1.0] — 0.0 = every expected category present,
    1.0 = nothing present (or everything present but still capped by the
    incident penalty at the theoretical max).
    """
    weights = category_weights or EXPECTED_CATEGORY_WEIGHTS
    expected = sorted(weights.keys())
    missing = sorted(c for c in expected if c not in present_categories)

    weighted_total = sum(weights.values())
    weighted_missing = sum(weights[c] for c in missing)
    base_score = (weighted_missing / weighted_total) if weighted_total > 0 else 0.0

    # Penalty applies when the asset has recorded incidents but has
    # NEITHER "procedure" nor "manual" documentation present at all.
    penalty_applied = incident_count > 0 and _PROCEDURE_CATEGORIES.isdisjoint(present_categories)

    score = base_score + (INCIDENT_WITHOUT_PROCEDURE_PENALTY if penalty_applied else 0.0)
    score = round(min(1.0, max(0.0, score)), 4)

    return score, missing, expected, penalty_applied


async def get_asset_gap(db: AsyncSession, asset_id: str) -> Optional[tuple[AssetKnowledgeGap, str]]:
    result = await db.execute(
        select(AssetKnowledgeGap, Asset.name)
        .join(Asset, Asset.id == AssetKnowledgeGap.asset_id)
        .where(AssetKnowledgeGap.asset_id == asset_id)
    )
    row = result.first()
    return (row[0], row[1]) if row else None


async def list_asset_gaps(
    db: AsyncSession,
    min_gap_score: float = 0.0,
    limit: int = 100,
) -> list[tuple[AssetKnowledgeGap, str]]:
    """Sorted by gap_score descending — worst-documented assets first (for a dashboard)."""
    result = await db.execute(
        select(AssetKnowledgeGap, Asset.name)
        .join(Asset, Asset.id == AssetKnowledgeGap.asset_id)
        .where(AssetKnowledgeGap.gap_score >= min_gap_score)
        .order_by(AssetKnowledgeGap.gap_score.desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in result.all()]
