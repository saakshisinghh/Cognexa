"""
apps/api/workers/gap_tasks.py

Phase 6 — Knowledge Gap Detection: nightly Celery task.

Sync pattern (SessionLocal via session_scope()), matching
workers/cleanup_tasks.py and workers/temporal_tasks.py exactly.

Scheduled to run AFTER workers/temporal_tasks.py::flag_stale_documents
in celery_app.py's beat schedule, since "is this category documented"
here means "has at least one non-stale completed document in that
category" — reusing Phase 6 Feature 1's is_stale flag rather than
re-deriving staleness independently.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery import shared_task

from apps.api.models import Asset, Document, DocumentStatus, AssetKnowledgeGap
from apps.api.models.incident import Incident
from apps.api.services.gap import compute_gap_score
from apps.api.workers._helpers import session_scope

logger = logging.getLogger("indusmind.workers.gap")


@shared_task(name="apps.api.workers.gap_tasks.compute_knowledge_gaps")
def compute_knowledge_gaps_task():
    """
    For every asset: determine which expected documentation categories
    have at least one completed, non-stale document; count incidents;
    compute GapScore via services/gap.py; upsert the asset's single
    asset_knowledge_gaps row.
    """
    now = datetime.now(timezone.utc)
    processed = 0

    with session_scope() as db:
        assets = db.query(Asset).filter(Asset.is_active.is_(True)).all()

        for asset in assets:
            present_docs = (
                db.query(Document.category)
                .filter(
                    Document.asset_id == asset.id,
                    Document.status == DocumentStatus.completed,
                    Document.is_stale.is_(False),
                    Document.category.isnot(None),
                )
                .distinct()
                .all()
            )
            present_categories = {row[0] for row in present_docs if row[0]}

            incident_count = db.query(Incident).filter(Incident.asset_id == asset.id).count()

            gap_score, missing, expected, penalty_applied = compute_gap_score(
                present_categories=present_categories,
                incident_count=incident_count,
            )

            gap_row = db.query(AssetKnowledgeGap).filter(AssetKnowledgeGap.asset_id == asset.id).first()
            if gap_row is None:
                gap_row = AssetKnowledgeGap(asset_id=asset.id)
                db.add(gap_row)

            gap_row.gap_score = gap_score
            gap_row.missing_categories = missing
            gap_row.present_categories = sorted(present_categories)
            gap_row.expected_categories = expected
            gap_row.incident_count = incident_count
            gap_row.incident_penalty_applied = int(penalty_applied)
            gap_row.computed_at = now

            processed += 1

    logger.info("compute_knowledge_gaps_task complete: assets_processed=%d", processed)
    return {"assets_processed": processed}
