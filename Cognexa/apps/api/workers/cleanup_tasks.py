"""
Periodic maintenance tasks, scheduled via Celery beat (see celery_app.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task

from apps.api.config import settings
from apps.api.models import (
    Document, DocumentStatus, ProcessingJob, JobStatus, QueueStatistics, WorkerStatus,
)
from apps.api.workers._helpers import session_scope

logger = logging.getLogger("indusmind.workers.cleanup")


@shared_task(name="apps.api.workers.cleanup_tasks.cleanup_temp_files")
def cleanup_temp_files():
    """
    Removes orphaned MinIO objects for documents whose DB row no longer exists
    (e.g. a delete that happened while a worker still held the file), and any
    document rows stuck in `pending` past the temp-file retention window
    with no associated job (upload that never got queued).
    """
    from apps.api.routers.documents import get_minio_client
    from apps.api.config import settings as cfg

    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.TEMP_FILE_MAX_AGE_HOURS)
    removed = 0
    with session_scope() as db:
        stale_docs = (
            db.query(Document)
            .filter(Document.status == DocumentStatus.pending, Document.created_at < cutoff)
            .all()
        )
        for doc in stale_docs:
            has_job = db.query(ProcessingJob).filter(ProcessingJob.document_id == doc.id).first()
            if has_job:
                continue
            try:
                minio = get_minio_client()
                minio.remove_object(cfg.MINIO_BUCKET, doc.filename)
            except Exception as e:
                logger.warning(f"Failed to remove orphaned object for {doc.id}: {e}")
            doc.status = DocumentStatus.failed
            doc.error_message = "Upload never queued for processing; auto-marked failed by cleanup"
            removed += 1

    logger.info(f"cleanup_temp_files: marked {removed} stale uploads")
    return {"cleaned": removed}


@shared_task(name="apps.api.workers.cleanup_tasks.recover_stuck_jobs")
def recover_stuck_jobs():
    """
    Failed-task recovery: jobs stuck in `processing` for longer than the
    task time limit (i.e. the worker likely died mid-task) are automatically
    retried up to `max_retries`, otherwise marked failed for manual review.
    """
    stuck_cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.CELERY_TASK_TIME_LIMIT * 2)
    recovered, failed = 0, 0

    with session_scope() as db:
        stuck = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.status == JobStatus.processing, ProcessingJob.updated_at < stuck_cutoff)
            .all()
        )
        for job in stuck:
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = JobStatus.queued
                job.error_message = "Auto-recovered after worker timeout; re-queued"
                doc = db.query(Document).filter(Document.id == job.document_id).first()
                if doc:
                    try:
                        from apps.api.routers.documents import get_minio_client
                        from apps.api.workers.document_tasks import queue_document_pipeline
                        minio = get_minio_client()
                        obj = minio.get_object(settings.MINIO_BUCKET, doc.filename)
                        file_bytes = obj.read()
                        queue_document_pipeline(job.id, doc.id, file_bytes, doc.mime_type, doc.original_filename)
                        recovered += 1
                    except Exception as e:
                        logger.error(f"Failed to re-queue stuck job {job.id}: {e}")
                        job.status = JobStatus.failed
                        job.error_message = f"Recovery failed: {e}"
                        failed += 1
            else:
                job.status = JobStatus.failed
                job.error_message = "Exceeded max retries after worker timeout"
                failed += 1

    logger.info(f"recover_stuck_jobs: recovered={recovered} failed={failed}")
    return {"recovered": recovered, "failed": failed}


@shared_task(name="apps.api.workers.cleanup_tasks.purge_old_failed_jobs")
def purge_old_failed_jobs():
    """Dead-letter retention: hard-delete failed job rows older than the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.FAILED_JOB_RETENTION_DAYS)
    with session_scope() as db:
        deleted = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.status == JobStatus.failed, ProcessingJob.completed_at < cutoff)
            .delete(synchronize_session=False)
        )
    logger.info(f"purge_old_failed_jobs: deleted {deleted} jobs")
    return {"deleted": deleted}


@shared_task(name="apps.api.workers.cleanup_tasks.record_queue_statistics")
def record_queue_statistics():
    """Snapshots queue depth (pending/processing/completed/failed jobs) for the dashboard."""
    with session_scope() as db:
        for queue_name in ("documents", "ocr", "embedding", "cleanup"):
            pending = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.queued).count()
            processing = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.processing).count()
            completed = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.completed).count()
            failed = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.failed).count()
            db.add(QueueStatistics(
                queue_name=queue_name, pending_count=pending, processing_count=processing,
                completed_count=completed, failed_count=failed,
            ))
    return {"status": "recorded"}


@shared_task(name="apps.api.workers.cleanup_tasks.heartbeat")
def heartbeat(worker_name: str, hostname: str, active_tasks: int, processed_tasks: int, concurrency: int):
    """Called by a worker on startup/periodically (optional, wired via celery events consumer)."""
    with session_scope() as db:
        ws = db.query(WorkerStatus).filter(WorkerStatus.worker_name == worker_name).first()
        if not ws:
            ws = WorkerStatus(worker_name=worker_name)
            db.add(ws)
        ws.hostname = hostname
        ws.status = "online"
        ws.active_tasks = active_tasks
        ws.processed_tasks = processed_tasks
        ws.concurrency = concurrency
        ws.last_heartbeat = datetime.now(timezone.utc)
    return {"status": "ok"}

@shared_task(name="apps.api.workers.cleanup_tasks.record_worker_heartbeats")
def record_worker_heartbeats():
    """
    Polls Celery's own runtime inspection API for all currently connected
    workers and upserts a WorkerStatus row for each. This is what actually
    populates the Processing Dashboard's "Workers" panel — the heartbeat()
    task above was never called by anything on its own.
    """
    from apps.api.workers.celery_app import celery_app

    inspect = celery_app.control.inspect(timeout=2.0)
    stats = inspect.stats() or {}
    active = inspect.active() or {}

    if not stats:
        logger.warning("record_worker_heartbeats: no workers responded to inspect")
        return {"status": "no_workers"}

    for worker_name, worker_stats in stats.items():
        heartbeat(
            worker_name=worker_name,
            hostname=worker_name,
            active_tasks=len(active.get(worker_name, [])),
            processed_tasks=sum(worker_stats.get("total", {}).values()) if worker_stats.get("total") else 0,
            concurrency=worker_stats.get("pool", {}).get("max-concurrency", 0),
        )
    return {"status": "recorded", "workers": list(stats.keys())}