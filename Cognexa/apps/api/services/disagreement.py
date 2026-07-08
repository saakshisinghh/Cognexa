"""
apps/api/services/disagreement.py

Phase 6 — Expert Disagreement Detection.

Reuses Phase 4's services/retrieval/conflict_detector.py output — this
module does not run any new conflict-detection logic itself, it only
aggregates conflicts ALREADY detected and persisted per-query into
persistent, asset-scoped clusters. See workers/disagreement_tasks.py for
the nightly aggregation job that reads query_history.conflicts_json.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import AssetExpertDisagreement, Asset, User

SEVERITY_RANK = {"minor": 0, "moderate": 1, "major": 2}


def canonical_document_pair(doc_id_a: str, doc_id_b: str) -> tuple[str, str]:
    """
    Returns (doc_id_a, doc_id_b) sorted so the same pair is always stored
    in the same order regardless of which document a given conflict
    happened to list first (ConflictFlag.chunk_a vs .chunk_b is
    order-arbitrary — it depends on retrieval rank, not document identity).
    """
    return tuple(sorted((doc_id_a, doc_id_b)))  # type: ignore[return-value]


def higher_severity(a: str, b: str) -> str:
    return a if SEVERITY_RANK.get(a, 0) >= SEVERITY_RANK.get(b, 0) else b


async def get_asset_disagreements(
    db: AsyncSession,
    asset_id: str,
    include_resolved: bool = False,
) -> list[AssetExpertDisagreement]:
    query = select(AssetExpertDisagreement).where(AssetExpertDisagreement.asset_id == asset_id)
    if not include_resolved:
        query = query.where(AssetExpertDisagreement.is_resolved.is_(False))
    query = query.order_by(AssetExpertDisagreement.occurrence_count.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_disagreements(
    db: AsyncSession,
    include_resolved: bool = False,
    limit: int = 100,
) -> list[tuple[AssetExpertDisagreement, str]]:
    """Returns (disagreement, asset_name) tuples, sorted by occurrence_count descending."""
    query = (
        select(AssetExpertDisagreement, Asset.name)
        .join(Asset, Asset.id == AssetExpertDisagreement.asset_id)
    )
    if not include_resolved:
        query = query.where(AssetExpertDisagreement.is_resolved.is_(False))
    query = query.order_by(AssetExpertDisagreement.occurrence_count.desc()).limit(limit)
    result = await db.execute(query)
    return [(row[0], row[1]) for row in result.all()]


async def resolve_disagreement(
    db: AsyncSession,
    disagreement_id: str,
    resolved_by_user_id: str,
    notes: Optional[str],
) -> AssetExpertDisagreement:
    result = await db.execute(
        select(AssetExpertDisagreement).where(AssetExpertDisagreement.id == disagreement_id)
    )
    disagreement = result.scalar_one_or_none()
    if disagreement is None:
        raise ValueError(f"Disagreement {disagreement_id} not found.")

    disagreement.is_resolved = True
    disagreement.resolved_by_user_id = resolved_by_user_id
    disagreement.resolved_at = datetime.now(timezone.utc)
    disagreement.resolution_notes = notes

    await db.commit()
    await db.refresh(disagreement)
    return disagreement
