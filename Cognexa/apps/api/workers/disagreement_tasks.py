"""
apps/api/workers/disagreement_tasks.py

Phase 6 — Expert Disagreement Detection: nightly Celery task.

Sync pattern (SessionLocal via session_scope()), matching the other
Phase 6 nightly tasks.

Reads query_history.conflicts_json (populated per-query by Phase 4's
services/retrieval/conflict_detector.py via services/copilot_v2.py's
_persist_query). There is no SQLAlchemy ORM model for query_history —
it was created and is accessed via raw SQL throughout this codebase
(see services/copilot_v2.py::_persist_query) — this task follows that
same existing convention rather than introducing a new ORM model for it.

Full rescan every run (not incremental) — at current expected data
volumes this is simpler and more robust than tracking a "processed since"
watermark, and it naturally self-corrects if a previous run partially
failed.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import text

from apps.api.models import Chunk, Document, AssetExpertDisagreement
from apps.api.services.disagreement import canonical_document_pair, higher_severity
from apps.api.workers._helpers import session_scope

logger = logging.getLogger("indusmind.workers.disagreement")


@shared_task(name="apps.api.workers.disagreement_tasks.detect_expert_disagreements")
def detect_expert_disagreements_task():
    now = datetime.now(timezone.utc)
    clusters_updated = 0

    with session_scope() as db:
        rows = db.execute(
            text("SELECT conflicts_json, created_at FROM query_history WHERE conflict_detected = TRUE")
        ).fetchall()

        if not rows:
            logger.info("detect_expert_disagreements_task: no conflicted queries found")
            return {"clusters_updated": 0}

        # Collect every chunk_id mentioned across all historical conflicts
        # in one pass, then resolve chunk_id -> (document_id, title,
        # asset_id) in a single batch query, rather than one query per
        # conflict per row.
        all_conflicts: list[dict] = []
        chunk_ids: set[str] = set()
        for row in rows:
            try:
                conflicts = json.loads(row.conflicts_json) if row.conflicts_json else []
            except (json.JSONDecodeError, TypeError):
                continue
            for c in conflicts:
                c["_row_created_at"] = row.created_at
                all_conflicts.append(c)
                chunk_ids.add(str(c.get("chunk_a_id")))
                chunk_ids.add(str(c.get("chunk_b_id")))

        if not all_conflicts:
            logger.info("detect_expert_disagreements_task: no parseable conflicts found")
            return {"clusters_updated": 0}

        chunk_lookup = (
            db.query(Chunk.id, Chunk.document_id, Document.asset_id)
            .join(Document, Document.id == Chunk.document_id)
            .filter(Chunk.id.in_(chunk_ids))
            .all()
        )
        chunk_to_doc: dict[str, str] = {c_id: doc_id for c_id, doc_id, _ in chunk_lookup}
        chunk_to_asset: dict[str, str] = {c_id: asset_id for c_id, doc_id, asset_id in chunk_lookup if asset_id}

        # Cluster: (asset_id, canonical_doc_pair, topic) -> aggregate
        clusters: dict[tuple, dict] = {}

        for c in all_conflicts:
            chunk_a_id = str(c.get("chunk_a_id"))
            chunk_b_id = str(c.get("chunk_b_id"))
            doc_a_id = chunk_to_doc.get(chunk_a_id)
            doc_b_id = chunk_to_doc.get(chunk_b_id)
            asset_id = chunk_to_asset.get(chunk_a_id) or chunk_to_asset.get(chunk_b_id)

            # Skip conflicts we can't fully resolve — e.g. a chunk that
            # was deleted since the query ran, or a document with no
            # asset assigned. Expert Disagreement Detection is asset-
            # scoped by design, so an unresolvable asset means this
            # conflict can't be clustered.
            if not (doc_a_id and doc_b_id and asset_id):
                continue

            pair = canonical_document_pair(doc_a_id, doc_b_id)
            topic = c.get("topic", "unknown")
            key = (asset_id, pair, topic)

            # document_a/_b_title in the stored dict follow the original
            # chunk_a/chunk_b ordering, which may not match the canonical
            # pair order — resolve titles by matching doc id, not position.
            title_by_doc_id = {
                doc_a_id: c.get("chunk_a_document_title", ""),
                doc_b_id: c.get("chunk_b_document_title", ""),
            }
            excerpt_by_doc_id = {
                doc_a_id: c.get("chunk_a_excerpt", ""),
                doc_b_id: c.get("chunk_b_excerpt", ""),
            }

            entry = clusters.get(key)
            if entry is None:
                clusters[key] = {
                    "occurrence_count": 1,
                    "max_severity": c.get("severity", "minor"),
                    "sample_excerpt_a": excerpt_by_doc_id.get(pair[0], ""),
                    "sample_excerpt_b": excerpt_by_doc_id.get(pair[1], ""),
                    "document_a_title": title_by_doc_id.get(pair[0], ""),
                    "document_b_title": title_by_doc_id.get(pair[1], ""),
                    "last_seen_at": c.get("_row_created_at"),
                }
            else:
                entry["occurrence_count"] += 1
                entry["max_severity"] = higher_severity(entry["max_severity"], c.get("severity", "minor"))
                row_created_at = c.get("_row_created_at")
                if row_created_at and (entry["last_seen_at"] is None or row_created_at > entry["last_seen_at"]):
                    entry["last_seen_at"] = row_created_at
                    entry["sample_excerpt_a"] = excerpt_by_doc_id.get(pair[0], entry["sample_excerpt_a"])
                    entry["sample_excerpt_b"] = excerpt_by_doc_id.get(pair[1], entry["sample_excerpt_b"])

        for (asset_id, (doc_a_id, doc_b_id), topic), agg in clusters.items():
            existing = (
                db.query(AssetExpertDisagreement)
                .filter(
                    AssetExpertDisagreement.asset_id == asset_id,
                    AssetExpertDisagreement.document_a_id == doc_a_id,
                    AssetExpertDisagreement.document_b_id == doc_b_id,
                    AssetExpertDisagreement.topic == topic,
                )
                .first()
            )

            if existing is None:
                db.add(AssetExpertDisagreement(
                    asset_id=asset_id,
                    topic=topic,
                    document_a_id=doc_a_id,
                    document_a_title=agg["document_a_title"],
                    document_b_id=doc_b_id,
                    document_b_title=agg["document_b_title"],
                    occurrence_count=agg["occurrence_count"],
                    max_severity=agg["max_severity"],
                    sample_excerpt_a=agg["sample_excerpt_a"],
                    sample_excerpt_b=agg["sample_excerpt_b"],
                    last_seen_at=agg["last_seen_at"],
                    is_resolved=False,
                    computed_at=now,
                ))
            else:
                existing.occurrence_count = agg["occurrence_count"]
                existing.max_severity = higher_severity(existing.max_severity, agg["max_severity"])
                existing.last_seen_at = agg["last_seen_at"]
                existing.sample_excerpt_a = agg["sample_excerpt_a"]
                existing.sample_excerpt_b = agg["sample_excerpt_b"]
                existing.computed_at = now

                # Auto-reopen: if this cluster was marked resolved but a
                # new occurrence appeared afterward, the disagreement is
                # still live — whatever fix was applied didn't take.
                if (
                    existing.is_resolved
                    and existing.resolved_at
                    and agg["last_seen_at"]
                    and agg["last_seen_at"] > existing.resolved_at
                ):
                    existing.is_resolved = False
                    existing.resolution_notes = (
                        (existing.resolution_notes or "")
                        + f"\n[Auto-reopened {now.date().isoformat()}: new occurrence detected after resolution.]"
                    )

            clusters_updated += 1

    logger.info("detect_expert_disagreements_task complete: clusters_updated=%d", clusters_updated)
    return {"clusters_updated": clusters_updated}
