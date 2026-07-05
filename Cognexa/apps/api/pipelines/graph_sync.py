"""
apps/api/pipelines/graph_sync.py

Purpose
-------
Celery tasks that sync Postgres records (Asset, Incident, Document,
Inspection) into the Neo4j graph. Triggered on incident create/update
(Step 6 router) and runnable as a periodic reconciliation job.

This is the file referenced as "pipelines/graph_sync.py" in the roadmap
and as "Celery Graph Sync" in the feature list.

Dependencies
------------
- apps/api/workers/celery_app.py (assumed to exist from Phase 2 — REUSED,
  not redefined; we only register new tasks on the existing Celery app)
- apps/api/services/graph.py
- apps/api/db.py (SessionLocal — existing Postgres session factory)
- apps/api/models/incident.py
- apps/api/ontology/schema.py (failure_modes.csv seeding)

This file is NEW.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from apps.api.db import SessionLocal  # existing Phase 1 Postgres session factory
from apps.api.models.incident import Incident
from apps.api.ontology.schema import NodeLabel, apply_graph_schema
from apps.api.services.graph import graph_service
from apps.api.services.graph_repository import graph_repository

logger = logging.getLogger("indusmind.graph.sync")

FAILURE_MODES_CSV = Path(__file__).resolve().parent.parent / "ontology" / "failure_modes.csv"


# ---------------------------------------------------------------------------
# Startup / idempotent schema + seed tasks
# ---------------------------------------------------------------------------
@shared_task(name="graph.apply_schema")
def apply_schema_task() -> dict:
    """Run once on deploy (also called directly at API startup, see Step 6)."""
    return apply_graph_schema()


@shared_task(name="graph.seed_failure_modes")
def seed_failure_modes_task() -> dict:
    """Idempotent — MERGE means re-running is always safe."""
    seeded = 0
    with FAILURE_MODES_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            graph_repository.upsert_node(
                NodeLabel.FAILURE_MODE,
                "code",
                row["code"],
                {"label": row["label"], "category": row["category"], "description": row["description"]},
            )
            seeded += 1
    logger.info("Seeded %d failure modes into Neo4j", seeded)
    return {"seeded": seeded}


# ---------------------------------------------------------------------------
# Per-record sync tasks (triggered on create/update from the router)
# ---------------------------------------------------------------------------
@shared_task(
    name="graph.sync_incident",
    bind=True,
    max_retries=5,
    default_retry_delay=10,  # seconds, exponential-ish via retry count
    acks_late=True,
)
def sync_incident_task(self, incident_id: str) -> dict:
    """
    Pulls the Incident row from Postgres and pushes it (+ its Asset/Document
    relationships) into Neo4j. Retries on transient Neo4j unavailability;
    marks graph_sync_status='failed' in Postgres if retries are exhausted
    so it surfaces in monitoring instead of failing silently.
    """
    db = SessionLocal()
    incident: Optional[Incident] = None
    try:
        incident = db.get(Incident, incident_id)
        if incident is None:
            logger.error("sync_incident_task: incident %s not found in Postgres", incident_id)
            return {"status": "skipped", "reason": "not_found"}

        graph_service.sync_incident_node(
            incident_id=str(incident.id),
            title=incident.title,
            asset_id=str(incident.asset_id),
            occurred_at_iso=incident.occurred_at.isoformat(),
            document_id=str(incident.document_id) if incident.document_id else None,
            failure_mode_code=incident.failure_mode_code,
            extra_properties={
                "severity": incident.severity.value,
                "status": incident.status.value,
            },
        )

        incident.graph_sync_status = "synced"
        incident.graph_synced_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Synced incident %s to Neo4j", incident_id)
        return {"status": "synced", "incident_id": incident_id}

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if incident is not None:
            incident.graph_sync_status = "failed"
            db.commit()
        logger.exception("Failed to sync incident %s, attempt %d", incident_id, self.request.retries)
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.error("Max retries exceeded syncing incident %s — left as graph_sync_status=failed", incident_id)
            return {"status": "failed", "incident_id": incident_id, "error": str(exc)}
    finally:
        db.close()


@shared_task(name="graph.sync_asset", bind=True, max_retries=5, default_retry_delay=10, acks_late=True)
def sync_asset_task(self, asset_id: str, name: str, site_id: Optional[str] = None) -> dict:
    """Assumes an Asset model already exists from Phase 1 — only graph-syncs it here."""
    try:
        graph_service.sync_asset_node(asset_id=asset_id, name=name, site_id=site_id)
        return {"status": "synced", "asset_id": asset_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to sync asset %s", asset_id)
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            return {"status": "failed", "asset_id": asset_id, "error": str(exc)}


# ---------------------------------------------------------------------------
# Similarity computation — periodic task (Celery beat, e.g. nightly)
# ---------------------------------------------------------------------------
@shared_task(name="graph.compute_asset_similarity")
def compute_asset_similarity_task(min_shared_relationships: int = 2, top_k: int = 10) -> dict:
    """
    Computes SIMILAR_TO edges between Assets that share FailureMode or
    ComplianceRule relationships above a threshold. Simple co-occurrence
    scoring — sufficient for Phase 3; replaced by embedding-based
    similarity in a later phase if needed.
    """
    query = """
    MATCH (a:Asset)-[:CAUSED_BY|SUBJECT_TO]-(shared)-[:CAUSED_BY|SUBJECT_TO]-(b:Asset)
    WHERE elementId(a) < elementId(b)
    WITH a, b, count(DISTINCT shared) AS shared_count
    WHERE shared_count >= $min_shared
    RETURN elementId(a) AS a_id, elementId(b) AS b_id, shared_count
    ORDER BY shared_count DESC
    LIMIT $limit
    """
    from apps.api.db_graph import neo4j_session  # local import avoids circular import at module load

    pairs_processed = 0
    with neo4j_session() as session:
        results = list(session.run(query, min_shared=min_shared_relationships, limit=top_k * 50))
        for record in results:
            score = min(record["shared_count"] / 5.0, 1.0)  # normalize, cap at 1.0
            graph_repository.create_similarity_edge(
                record["a_id"], record["b_id"], score, record["shared_count"]
            )
            pairs_processed += 1

    logger.info("Computed %d SIMILAR_TO edges", pairs_processed)
    return {"pairs_processed": pairs_processed}
