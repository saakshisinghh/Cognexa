"""
OCR Processing worker task.
Wraps the existing `services/ocr.py` (Phase 1, untouched) in a retryable Celery task.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from apps.api.config import settings
from apps.api.models import Document, DocumentStatus, JobStatus, JobStep, TaskState
from apps.api.workers._helpers import session_scope, update_job, record_task_execution
from apps.api.services import ocr as ocr_svc

logger = logging.getLogger("indusmind.workers.ocr")


@shared_task(
    bind=True,
    name="apps.api.workers.ocr_tasks.run_ocr",
    autoretry_for=(Exception,),
    retry_backoff=settings.CELERY_TASK_RETRY_BACKOFF,
    retry_backoff_max=settings.CELERY_TASK_RETRY_BACKOFF_MAX,
    retry_jitter=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    acks_late=True,
)
def run_ocr(self, job_id: str, document_id: str, file_bytes_b64: str, mime_type: str, filename: str):
    """
    Extracts text + metadata from a document.
    Returns a small dict (full text is written straight to Postgres, not
    passed through the Celery result backend, to keep payloads small).
    """
    import base64
    started = datetime.now(timezone.utc)

    with session_scope() as db:
        update_job(db, job_id, status=JobStatus.processing, step=JobStep.ocr, progress=10,
                   celery_task_id=self.request.id)
        record_task_execution(db, job_id, self.request.id, self.name, "ocr",
                               TaskState.started, attempt=self.request.retries + 1, started_at=started)

    try:
        file_bytes = base64.b64decode(file_bytes_b64)
        result = ocr_svc.extract_text_and_metadata(file_bytes, mime_type, filename)

        with session_scope() as db:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.extracted_text = result["text"]
                doc.page_count = result["page_count"]
                doc.language = result["language"]
                doc.extra_metadata = {**(doc.extra_metadata or {}), **result["metadata"], "ocr_engine": result["ocr_engine"]}
                doc.ocr_status = "completed"
            finished = datetime.now(timezone.utc)
            update_job(db, job_id, progress=30, step=JobStep.entity_extraction)
            record_task_execution(db, job_id, self.request.id, self.name, "ocr",
                                   TaskState.success, started_at=started, finished_at=finished,
                                   result={"page_count": result["page_count"], "language": result["language"]})
        return {"status": "ok", "page_count": result["page_count"]}

    except SoftTimeLimitExceeded:
        logger.error(f"OCR soft time limit exceeded for document {document_id}")
        _mark_failed(self, job_id, document_id, started, "OCR exceeded time limit")
        raise
    except Exception as e:
        logger.error(f"OCR failed for document {document_id}: {e}")
        if self.request.retries >= self.max_retries:
            _mark_failed(self, job_id, document_id, started, f"OCR failed: {e}")
        else:
            with session_scope() as db:
                record_task_execution(db, job_id, self.request.id, self.name, "ocr",
                                       TaskState.retry, attempt=self.request.retries + 1,
                                       error=str(e), started_at=started)
        raise


def _mark_failed(task, job_id: str, document_id: str, started, message: str):
    finished = datetime.now(timezone.utc)
    with session_scope() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.failed
            doc.ocr_status = "failed"
            doc.error_message = message
        update_job(db, job_id, status=JobStatus.failed, error=message)
        record_task_execution(db, job_id, task.request.id, task.name, "ocr",
                               TaskState.failure, error=message, started_at=started, finished_at=finished)
