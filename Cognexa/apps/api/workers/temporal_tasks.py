"""
apps/api/workers/temporal_tasks.py

Phase 6 — Temporal Knowledge Intelligence: nightly Celery tasks.

Follows the exact sync pattern already used by workers/cleanup_tasks.py
(session_scope() + sync db.query()) — NOT the AsyncSession pattern used
by services/copilot_v2.py. Celery workers here are sync throughout; see
workers/_helpers.py::session_scope.

Three tasks, registered individually so a failure/slowness in one
(e.g. the Weaviate-backed supersession sweep) doesn't block the other two
from running on schedule:

    1. recompute_trust_scores_task   — recomputes every chunk's decayed
       trust_score and pushes it to both Postgres and Weaviate.
    2. flag_stale_documents_task     — must run AFTER (1) in the nightly
       schedule, since it reads the trust scores (1) just wrote.
    3. detect_superseded_chunks_task — Weaviate near-neighbor sweep that
       finds chunks in an older document that a newer document (same
       asset, same category) appears to replace.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from celery import shared_task
from weaviate.classes.query import Filter, MetadataQuery

from apps.api.models import Chunk, Document
from apps.api.services import decay
from apps.api.services.temporal import push_trust_score_to_weaviate
from apps.api.weaviate_client import get_weaviate_client
from apps.api.workers._helpers import session_scope

logger = logging.getLogger("indusmind.workers.temporal")

_CHUNK_CLASS = "DocumentChunk"
_BATCH_SIZE = 500
_STALE_THRESHOLD = 0.4
# How close two chunks' embeddings must be (Weaviate cosine distance,
# 0 = identical) to consider the older one superseded by the newer one.
# Deliberately conservative (very close match only) — a false "superseded"
# hides real information from retrieval, which is worse than missing one.
_SUPERSESSION_DISTANCE_THRESHOLD = 0.08


@shared_task(name="apps.api.workers.temporal_tasks.recompute_trust_scores")
def recompute_trust_scores_task():
    """
    Recomputes trust_score for every chunk, in batches, using
    services/decay.py's pure formula. Writes to Postgres (source of
    truth) and Weaviate (used by retrieval-time filtering) for each
    chunk. Already-superseded chunks (valid_to set) are recomputed too —
    their score stays capped at decay.SUPERSEDED_TRUST_CEILING.
    """
    now = datetime.now(timezone.utc)
    updated = 0
    offset = 0

    with session_scope() as db:
        while True:
            batch = (
                db.query(Chunk)
                .join(Document, Chunk.document_id == Document.id)
                .add_columns(Document.category)
                .order_by(Chunk.id)
                .offset(offset)
                .limit(_BATCH_SIZE)
                .all()
            )
            if not batch:
                break

            for chunk, category in batch:
                chunk.trust_score = decay.compute_trust_score(
                    chunk.valid_from, chunk.valid_to, category, now=now,
                )
                chunk.decay_computed_at = now
                push_trust_score_to_weaviate(chunk.weaviate_id, chunk.trust_score)
                updated += 1

            offset += _BATCH_SIZE

    logger.info("recompute_trust_scores_task complete: updated=%d", updated)
    return {"updated": updated}


@shared_task(name="apps.api.workers.temporal_tasks.flag_stale_documents")
def flag_stale_documents_task(threshold: float = _STALE_THRESHOLD):
    """
    Flags documents whose average chunk trust_score has dropped below
    `threshold` as stale. Should be scheduled to run AFTER
    recompute_trust_scores_task in the nightly beat schedule so it reads
    freshly-decayed scores, not yesterday's.
    """
    now = datetime.now(timezone.utc)
    flagged = 0
    unflagged = 0

    with session_scope() as db:
        documents = db.query(Document).all()
        for document in documents:
            trust_scores = [
                c.trust_score for c in
                db.query(Chunk.trust_score).filter(Chunk.document_id == document.id).all()
            ]
            is_stale = decay.is_document_stale(trust_scores, threshold=threshold)

            if is_stale and not document.is_stale:
                document.is_stale = True
                document.stale_flagged_at = now
                document.stale_reason = (
                    f"Average chunk trust_score fell below {threshold} "
                    f"(nightly decay recomputation, {now.date().isoformat()})."
                )
                flagged += 1
            elif not is_stale and document.is_stale:
                # Trust scores recovered (e.g. chunks manually re-validated
                # or a supersession was reversed) — clear the flag.
                document.is_stale = False
                document.stale_flagged_at = None
                document.stale_reason = None
                unflagged += 1

    logger.info("flag_stale_documents_task complete: flagged=%d unflagged=%d", flagged, unflagged)
    return {"flagged": flagged, "unflagged": unflagged}


@shared_task(name="apps.api.workers.temporal_tasks.detect_superseded_chunks")
def detect_superseded_chunks_task():
    """
    For each (asset_id, category) group with 2+ documents, compares the
    newest document's chunks against the OLDER document(s)' chunks via
    Weaviate near-neighbor search (near_object, restricted to the same
    asset_id + category, excluding the newer document itself). A very
    close match (distance < _SUPERSESSION_DISTANCE_THRESHOLD) marks the
    older chunk as superseded_by the newer one.

    This is a heuristic sweep, not a guarantee — it complements (does not
    replace) the manual override endpoint
    (PATCH /temporal/chunks/{chunk_id}/supersede) for cases it misses.
    Already-superseded chunks (valid_to already set) are skipped to avoid
    repeatedly re-processing them every night.
    """
    now = datetime.now(timezone.utc)
    superseded_count = 0

    with session_scope() as db:
        documents = (
            db.query(Document)
            .filter(Document.asset_id.isnot(None), Document.category.isnot(None))
            .order_by(Document.created_at.asc())
            .all()
        )

        groups: dict[tuple[str, str], list[Document]] = defaultdict(list)
        for doc in documents:
            groups[(doc.asset_id, doc.category)].append(doc)

        client = get_weaviate_client()
        collection = client.collections.get(_CHUNK_CLASS)

        for (asset_id, category), docs in groups.items():
            if len(docs) < 2:
                continue

            docs_sorted = sorted(docs, key=lambda d: d.created_at)
            newest_doc = docs_sorted[-1]
            older_docs = docs_sorted[:-1]
            older_doc_ids = {d.id for d in older_docs}

            newest_chunks = (
                db.query(Chunk)
                .filter(Chunk.document_id == newest_doc.id, Chunk.weaviate_id.isnot(None))
                .all()
            )

            for new_chunk in newest_chunks:
                try:
                    response = collection.query.near_object(
                        near_object=new_chunk.weaviate_id,
                        limit=3,
                        filters=Filter.by_property("document_id").not_equal(newest_doc.id),
                        return_metadata=MetadataQuery(distance=True),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "near_object lookup failed for chunk_id=%s weaviate_id=%s error=%s",
                        new_chunk.id, new_chunk.weaviate_id, exc,
                    )
                    continue

                for obj in response.objects:
                    candidate_doc_id = obj.properties.get("document_id")
                    if candidate_doc_id not in older_doc_ids:
                        continue
                    distance = obj.metadata.distance
                    if distance is None or distance >= _SUPERSESSION_DISTANCE_THRESHOLD:
                        continue

                    old_chunk = db.query(Chunk).filter(Chunk.id == str(obj.uuid)).first()
                    if old_chunk is None or old_chunk.valid_to is not None:
                        continue  # not found locally, or already superseded — skip

                    old_chunk.valid_to = now
                    old_chunk.superseded_by_chunk_id = new_chunk.id
                    old_chunk.trust_score = decay.compute_trust_score(
                        old_chunk.valid_from, old_chunk.valid_to, category, now=now,
                    )
                    old_chunk.decay_computed_at = now
                    push_trust_score_to_weaviate(old_chunk.weaviate_id, old_chunk.trust_score)
                    superseded_count += 1

    logger.info("detect_superseded_chunks_task complete: superseded=%d", superseded_count)
    return {"superseded": superseded_count}
