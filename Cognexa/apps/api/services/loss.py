"""
apps/api/services/loss.py

Phase 6 — Knowledge Loss Prediction.

Ownership concentration is computed from REAL, EXISTING data:
    Document.owner_id  (who uploaded/owns each of an asset's documents)
    Incident.reported_by (who reported/handled each of an asset's incidents)

"Retirement risk" itself is NOT derivable from anything in this schema
(no hire_date/tenure anywhere) — see User.is_retirement_risk in
models/__init__.py's Phase 6 section. This module combines the organic
concentration signal with that manual flag; it does not fabricate a
retirement date or tenure estimate.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import AssetKnowledgeLossRisk, AssetExpertiseOwnership, Asset, User, AssetKnowledgeGap

# Incidents weighted higher than documents in the activity score — actually
# having handled a failure is stronger evidence of hands-on expertise than
# having uploaded a document about it.
DOCUMENT_ACTIVITY_WEIGHT = 1.0
INCIDENT_ACTIVITY_WEIGHT = 1.5

# Flat boost added to risk_score when the primary owner is manually
# flagged is_retirement_risk=True. Larger than the incident-without-
# procedure penalty in gap.py (0.15) because a confirmed HR signal is
# stronger evidence than an inferred one.
RETIREMENT_FLAG_BOOST = 0.25

RISK_LEVEL_THRESHOLDS = (
    (0.75, "critical"),
    (0.50, "high"),
    (0.25, "medium"),
    (0.0, "low"),
)


def compute_ownership_scores(
    doc_counts_by_user: dict[str, int],
    incident_counts_by_user: dict[str, int],
) -> dict[str, float]:
    """
    Returns {user_id: ownership_score} normalized so scores sum to 1.0
    across all users who have any activity on the asset. Empty dict if
    no one has any recorded activity yet.
    """
    all_user_ids = set(doc_counts_by_user) | set(incident_counts_by_user)
    activity = {
        uid: doc_counts_by_user.get(uid, 0) * DOCUMENT_ACTIVITY_WEIGHT
        + incident_counts_by_user.get(uid, 0) * INCIDENT_ACTIVITY_WEIGHT
        for uid in all_user_ids
    }
    total = sum(activity.values())
    if total <= 0:
        return {}
    return {uid: round(score / total, 4) for uid, score in activity.items()}


def compute_risk_score(
    concentration_score: float,
    contributor_count: int,
    primary_owner_is_retirement_risk: bool,
) -> tuple[float, str, bool]:
    """
    Returns (risk_score, risk_level, retirement_boost_applied).

    Base risk = concentration_score (0..1) — how much of the asset's
    knowledge sits with a single person. A flat +0.1 is added when
    contributor_count == 1 (literally no one else has touched this
    asset at all — the worst possible bus-factor case), on top of
    whatever concentration_score already reflects.
    """
    risk = concentration_score
    if contributor_count == 1:
        risk = min(1.0, risk + 0.10)

    retirement_boost_applied = False
    if primary_owner_is_retirement_risk:
        risk = min(1.0, risk + RETIREMENT_FLAG_BOOST)
        retirement_boost_applied = True

    risk = round(risk, 4)

    level = "low"
    for threshold, label in RISK_LEVEL_THRESHOLDS:
        if risk >= threshold:
            level = label
            break

    return risk, level, retirement_boost_applied


def build_mitigation_recommendation(
    risk_level: str,
    contributor_count: int,
    primary_owner_name: Optional[str],
    missing_categories: Optional[list[str]] = None,
) -> str:
    """
    Rule-based recommendation text. Reuses Phase 6 Feature 2's
    missing_categories (from AssetKnowledgeGap) when available, so the
    recommendation can point at concrete documentation gaps rather than
    a generic "write more docs" suggestion.
    """
    if risk_level == "low":
        return "No action needed — knowledge for this asset is reasonably distributed across contributors."

    parts = []
    owner_ref = primary_owner_name or "the primary contributor"

    if risk_level == "critical":
        parts.append(
            f"Urgent: {owner_ref} holds the large majority of this asset's documented knowledge "
            f"({contributor_count} total contributor{'s' if contributor_count != 1 else ''}). "
            "Schedule a knowledge-transfer session and assign a co-owner immediately."
        )
    elif risk_level == "high":
        parts.append(
            f"{owner_ref} is heavily relied upon for this asset. Assign a secondary reviewer to "
            "shadow the next 2-3 incidents or document reviews for this asset."
        )
    else:  # medium
        parts.append(
            f"{owner_ref} is a significant contributor for this asset. Consider pairing a second "
            "engineer on the next maintenance cycle."
        )

    if missing_categories:
        parts.append(
            f"This asset is also missing documentation in: {', '.join(missing_categories)} — "
            f"prioritizing these would reduce reliance on {owner_ref}'s undocumented knowledge."
        )

    return " ".join(parts)


async def get_asset_risk(db: AsyncSession, asset_id: str) -> Optional[tuple[AssetKnowledgeLossRisk, str, Optional[str]]]:
    """Returns (risk_row, asset_name, primary_owner_name_or_None)."""
    result = await db.execute(
        select(AssetKnowledgeLossRisk, Asset.name)
        .join(Asset, Asset.id == AssetKnowledgeLossRisk.asset_id)
        .where(AssetKnowledgeLossRisk.asset_id == asset_id)
    )
    row = result.first()
    if row is None:
        return None
    risk_row, asset_name = row

    owner_name = None
    if risk_row.primary_owner_user_id:
        owner_result = await db.execute(select(User.full_name).where(User.id == risk_row.primary_owner_user_id))
        owner_name = owner_result.scalar_one_or_none()

    return risk_row, asset_name, owner_name


async def list_asset_risks(
    db: AsyncSession,
    min_risk_score: float = 0.0,
    limit: int = 100,
) -> list[tuple[AssetKnowledgeLossRisk, str]]:
    result = await db.execute(
        select(AssetKnowledgeLossRisk, Asset.name)
        .join(Asset, Asset.id == AssetKnowledgeLossRisk.asset_id)
        .where(AssetKnowledgeLossRisk.risk_score >= min_risk_score)
        .order_by(AssetKnowledgeLossRisk.risk_score.desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in result.all()]


async def list_asset_owners(db: AsyncSession, asset_id: str) -> list[tuple[AssetExpertiseOwnership, str]]:
    """All contributors for an asset, sorted by ownership_score descending."""
    result = await db.execute(
        select(AssetExpertiseOwnership, User.full_name)
        .join(User, User.id == AssetExpertiseOwnership.user_id)
        .where(AssetExpertiseOwnership.asset_id == asset_id)
        .order_by(AssetExpertiseOwnership.ownership_score.desc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def set_user_retirement_flag(db: AsyncSession, user_id: str, flagged: bool, notes: Optional[str]) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"User {user_id} not found.")
    user.is_retirement_risk = flagged
    user.retirement_risk_notes = notes
    await db.commit()
    await db.refresh(user)
    return user
