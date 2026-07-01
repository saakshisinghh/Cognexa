"""
Embedding Generation + Vector Storage worker task.
Reuses the existing `services/embedder.py` and `services/chunker.py` (Phase 1, untouched).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from apps.api.config import settings
from apps.api.models import Document, Chunk, DocumentStatus, JobStatus, JobStep, TaskState
from apps.api.workers._helpers import session_scope, update_job, record_task_execution
from apps.api.services import chunker as chunker_svc
from apps.api.services import embedder as embedder_svc

logger = logging.getLogger("indusmind.workers.embedding")


@shared_task(
    bind=True,
    name="apps.api.workers.embedding_tasks.generate_embeddings",
    autoretry_for=(Exception,),
    retry_backoff=settings.CELERY_TASK_RETRY_BACKOFF,
    retry_backoff_max=settings.CELERY_TASK_RETRY_BACKOFF_MAX,
    retry_jitter=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    acks_late=True,
)
def generate_embeddings(self, job_id: str, document_id: str):
    """
    Chunk text -> embed -> store in Weaviate -> persist Chunk rows.
    Combined into one task since embed_and_store_chunks already streams
    straight to Weaviate; splitting chunking/embedding/storage into three
    separate Celery hops would force re-reading large chunk lists from the
    result backend for no benefit. Each sub-step is still tracked via the
    job's `current_step` field for dashboard visibility.
    """
    started = datetime.now(timezone.utc)
    with session_scope() as db:
        update_job(db, job_id, step=JobStep.chunking, progress=45, celery_task_id=self.request.id)
        record_task_execution(db, job_id, self.request.id, self.name, "embedding",
                               TaskState.started, attempt=self.request.retries + 1, started_at=started)

    try:
        with session_scope() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                raise ValueError(f"Document {document_id} not found")
            text = doc.extracted_text or ""
            asset_id = doc.asset_id
            source = doc.original_filename

        chunks = chunker_svc.split_text(text=text, document_id=document_id, source=source)

        with session_scope() as db:
            db.query(Chunk).filter(Chunk.document_id == document_id).delete()
            db_chunks = [
                Chunk(
                    document_id=document_id,
                    chunk_index=ch.chunk_index,
                    text=ch.text,
                    page_number=ch.page_number,
                    token_count=ch.token_count,
                   extra_metadata=ch.metadata,
                )
                for ch in chunks
            ]
            db.bulk_save_objects(db_chunks)
            doc = db.query(Document).filter(Document.id == document_id).first()
            doc.chunk_count = len(chunks)
            update_job(db, job_id, step=JobStep.embedding, progress=65)

        # Embedding + vector storage
        from apps.api.weaviate_client import get_weaviate_client
        wv_client = get_weaviate_client()
        wv_ids = embedder_svc.embed_and_store_chunks(
            chunks=chunks, document_id=document_id, asset_id=asset_id,
            source=source, weaviate_client=wv_client,
        )

        with session_scope() as db:
            saved_chunks = (
                db.query(Chunk)
                .filter(Chunk.document_id == document_id)
                .order_by(Chunk.chunk_index)
                .all()
            )
            for db_chunk, wv_id in zip(saved_chunks, wv_ids):
                db_chunk.weaviate_id = wv_id

            doc = db.query(Document).filter(Document.id == document_id).first()
            doc.embedding_status = "completed"
            doc.status = DocumentStatus.completed
            update_job(db, job_id, status=JobStatus.completed, step=JobStep.done, progress=100)

            finished = datetime.now(timezone.utc)
            record_task_execution(db, job_id, self.request.id, self.name, "embedding",
                                   TaskState.success, started_at=started, finished_at=finished,
                                   result={"chunk_count": len(chunks), "vectors_stored": len(wv_ids)})

        logger.info(f"Document {document_id} processing complete ({len(chunks)} chunks)")
        return {"status": "ok", "chunk_count": len(chunks)}

    except SoftTimeLimitExceeded:
        _mark_failed(self, job_id, document_id, started, "Embedding step exceeded time limit")
        raise
    except Exception as e:
        logger.error(f"Embedding failed for document {document_id}: {e}")
        if self.request.retries >= self.max_retries:
            _mark_failed(self, job_id, document_id, started, f"Embedding failed: {e}")
        else:
            with session_scope() as db:
                record_task_execution(db, job_id, self.request.id, self.name, "embedding",
                                       TaskState.retry, attempt=self.request.retries + 1,
                                       error=str(e), started_at=started)
        raise


def _mark_failed(task, job_id: str, document_id: str, started, message: str):
    finished = datetime.now(timezone.utc)
    with session_scope() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.failed
            doc.embedding_status = "failed"
            doc.error_message = message
        update_job(db, job_id, status=JobStatus.failed, error=message)
        record_task_execution(db, job_id, task.request.id, task.name, "embedding",
                               TaskState.failure, error=message, started_at=started, finished_at=finished)
