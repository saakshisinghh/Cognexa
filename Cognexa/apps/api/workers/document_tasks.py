"""
Document pipeline orchestrator.

`process_document_async` is the single entry point queued by the upload
router. It performs entity extraction itself (cheap/fast) and then chains
into the OCR -> embedding tasks. Using `celery.chain` gives us per-step
retry isolation while keeping one ProcessingJob row as the source of truth
for overall progress.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone

from celery import shared_task, chain

from apps.api.config import settings
from apps.api.models import Document, JobStatus, JobStep, TaskState
from apps.api.workers._helpers import session_scope, update_job, record_task_execution, write_audit_event
from apps.api.workers.ocr_tasks import run_ocr
from apps.api.workers.embedding_tasks import generate_embeddings
from apps.api.services import extractor as extractor_svc

logger = logging.getLogger("indusmind.workers.document")


def queue_document_pipeline(job_id: str, document_id: str, file_bytes: bytes, mime_type: str, filename: str) -> str:
    """
    Called synchronously from the upload router (fast, no I/O besides the
    Celery enqueue itself). Returns the Celery task id of the first task in
    the chain so it can be stored on the ProcessingJob immediately.
    """
    file_b64 = base64.b64encode(file_bytes).decode("ascii")

    workflow = chain(
        run_ocr.s(job_id, document_id, file_b64, mime_type, filename),
        extract_entities_task.si(job_id, document_id),
        generate_embeddings.si(job_id, document_id),
    )
    async_result = workflow.apply_async(queue="documents")

    with session_scope() as db:
        update_job(db, job_id, status=JobStatus.queued, celery_task_id=async_result.id)
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = doc.status  # no-op, kept for clarity of pipeline ownership

    return async_result.id


@shared_task(
    bind=True,
    name="apps.api.workers.document_tasks.extract_entities_task",
    autoretry_for=(Exception,),
    retry_backoff=settings.CELERY_TASK_RETRY_BACKOFF,
    retry_backoff_max=settings.CELERY_TASK_RETRY_BACKOFF_MAX,
    retry_jitter=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    acks_late=True,
)
def extract_entities_task(self, job_id: str, document_id: str):
    started = datetime.now(timezone.utc)
    with session_scope() as db:
        update_job(db, job_id, step=JobStep.entity_extraction, progress=35)
        record_task_execution(db, job_id, self.request.id, self.name, "documents",
                               TaskState.started, attempt=self.request.retries + 1, started_at=started)
    try:
        with session_scope() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            text = doc.extracted_text or "" if doc else ""

        entities = extractor_svc.extract_entities(text)

        with session_scope() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.entity_count = len(entities)
                doc.extra_metadata = {**(doc.extra_metadata or {}), "entities": entities[:50]}
            finished = datetime.now(timezone.utc)
            record_task_execution(db, job_id, self.request.id, self.name, "documents",
                                   TaskState.success, started_at=started, finished_at=finished,
                                   result={"entity_count": len(entities)})
        return {"status": "ok", "entity_count": len(entities)}
    except Exception as e:
        # Entity extraction is best-effort; never fail the whole pipeline for it.
        logger.warning(f"Entity extraction failed for {document_id}, continuing pipeline: {e}")
        with session_scope() as db:
            finished = datetime.now(timezone.utc)
            record_task_execution(db, job_id, self.request.id, self.name, "documents",
                                   TaskState.failure, error=str(e), started_at=started, finished_at=finished)
        return {"status": "skipped", "error": str(e)}


@shared_task(name="apps.api.workers.document_tasks.cancel_job")
def cancel_job(job_id: str):
    """Best-effort cancellation: revokes the chained Celery task and marks the job cancelled."""
    from apps.api.workers.celery_app import celery_app as app

    with session_scope() as db:
        from apps.api.models import ProcessingJob
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            return {"status": "not_found"}
        if job.celery_task_id:
            app.control.revoke(job.celery_task_id, terminate=False)
        update_job(db, job_id, status=JobStatus.cancelled)
        write_audit_event(action="cancel_task", resource=f"job:{job_id}")
    return {"status": "cancelled"}
