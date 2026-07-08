"""
apps/api/workers/loss_tasks.py

Phase 6 — Knowledge Loss Prediction: nightly Celery task.

Sync pattern (SessionLocal via session_scope()), matching
workers/temporal_tasks.py and workers/gap_tasks.py exactly.

Scheduled to run AFTER gap_tasks.py (2:45) and temporal_tasks.py's
supersession sweep (3:00) in celery_app.py's beat schedule, since its
mitigation-recommendation text reads AssetKnowledgeGap.missing_categories
(Feature 2) when available.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import func as sa_func

from apps.api.models import (
    Asset, Document, User, AssetExpertiseOwnership, AssetKnowledgeLossRisk, AssetKnowledgeGap,
)
from apps.api.models.incident import Incident
from apps.api.services.loss import compute_ownership_scores, compute_risk_score, build_mitigation_recommendation
from apps.api.workers._helpers import session_scope

logger = logging.getLogger("indusmind.workers.loss")


@shared_task(name="apps.api.workers.loss_tasks.compute_knowledge_loss_risk")
def compute_knowledge_loss_risk_task():
    """
    For every asset: tally document/incident contributions per user,
    compute ownership_score per contributor, determine the primary
    owner and concentration_score, then compute the asset's overall
    knowledge-loss risk_score (boosted if the primary owner is manually
    flagged is_retirement_risk).
    """
    now = datetime.now(timezone.utc)
    assets_processed = 0

    with session_scope() as db:
        assets = db.query(Asset).filter(Asset.is_active.is_(True)).all()

        for asset in assets:
            doc_rows = (
                db.query(Document.owner_id, sa_func.count(Document.id))
                .filter(Document.asset_id == asset.id, Document.owner_id.isnot(None))
                .group_by(Document.owner_id)
                .all()
            )
            doc_counts = {uid: cnt for uid, cnt in doc_rows}

            incident_rows = (
                db.query(Incident.reported_by, sa_func.count(Incident.id))
                .filter(Incident.asset_id == asset.id, Incident.reported_by.isnot(None))
                .group_by(Incident.reported_by)
                .all()
            )
            incident_counts = {uid: cnt for uid, cnt in incident_rows}

            ownership_scores = compute_ownership_scores(doc_counts, incident_counts)

            # Clear stale per-user ownership rows for this asset, then
            # re-insert fresh ones — simpler and safer than diffing when
            # contributor sets can shrink (e.g. a document reassigned).
            db.query(AssetExpertiseOwnership).filter(AssetExpertiseOwnership.asset_id == asset.id).delete()

            primary_owner_id = None
            primary_owner_score = 0.0
            for user_id, score in ownership_scores.items():
                is_primary = score > primary_owner_score
                if is_primary:
                    primary_owner_id = user_id
                    primary_owner_score = score

                last_doc = (
                    db.query(sa_func.max(Document.updated_at))
                    .filter(Document.asset_id == asset.id, Document.owner_id == user_id)
                    .scalar()
                )
                last_incident = (
                    db.query(sa_func.max(Incident.updated_at))
                    .filter(Incident.asset_id == asset.id, Incident.reported_by == user_id)
                    .scalar()
                )
                last_activity = max([d for d in (last_doc, last_incident) if d is not None], default=None)

                db.add(AssetExpertiseOwnership(
                    asset_id=asset.id,
                    user_id=user_id,
                    document_count=doc_counts.get(user_id, 0),
                    incident_count=incident_counts.get(user_id, 0),
                    ownership_score=score,
                    is_primary_owner=False,  # set correctly below, after the loop
                    last_activity_at=last_activity,
                    computed_at=now,
                ))

            # Now that we know the true max, mark the primary owner row.
            if primary_owner_id is not None:
                db.flush()
                primary_row = (
                    db.query(AssetExpertiseOwnership)
                    .filter(
                        AssetExpertiseOwnership.asset_id == asset.id,
                        AssetExpertiseOwnership.user_id == primary_owner_id,
                    )
                    .first()
                )
                if primary_row is not None:
                    primary_row.is_primary_owner = True

            contributor_count = len(ownership_scores)
            primary_owner = db.query(User).filter(User.id == primary_owner_id).first() if primary_owner_id else None
            primary_owner_is_retirement_risk = bool(primary_owner and primary_owner.is_retirement_risk)

            risk_score, risk_level, boost_applied = compute_risk_score(
                concentration_score=primary_owner_score,
                contributor_count=contributor_count,
                primary_owner_is_retirement_risk=primary_owner_is_retirement_risk,
            )

            gap_row = db.query(AssetKnowledgeGap).filter(AssetKnowledgeGap.asset_id == asset.id).first()
            missing_categories = gap_row.missing_categories if gap_row else None

            mitigation = build_mitigation_recommendation(
                risk_level=risk_level,
                contributor_count=contributor_count,
                primary_owner_name=primary_owner.full_name if primary_owner else None,
                missing_categories=missing_categories,
            )

            risk_row = db.query(AssetKnowledgeLossRisk).filter(AssetKnowledgeLossRisk.asset_id == asset.id).first()
            if risk_row is None:
                risk_row = AssetKnowledgeLossRisk(asset_id=asset.id)
                db.add(risk_row)

            risk_row.primary_owner_user_id = primary_owner_id
            risk_row.concentration_score = primary_owner_score
            risk_row.contributor_count = contributor_count
            risk_row.retirement_boost_applied = boost_applied
            risk_row.risk_score = risk_score
            risk_row.risk_level = risk_level
            risk_row.mitigation_recommendation = mitigation
            risk_row.computed_at = now

            assets_processed += 1

    logger.info("compute_knowledge_loss_risk_task complete: assets_processed=%d", assets_processed)
    return {"assets_processed": assets_processed}
