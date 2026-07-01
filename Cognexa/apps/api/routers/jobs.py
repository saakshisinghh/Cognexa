"""
Processing Jobs Router — Phase 2.
Job status/listing, retry/cancel actions, queue + worker health, processing stats.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func as sqlfunc
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.models import (
    ProcessingJob, TaskExecution, JobStatus, Document, User, WorkerStatus, QueueStatistics,
)
from apps.api.routers.auth import get_current_user, require_engineer_or_admin
from apps.api.schemas.jobs import (
    ProcessingJobResponse, ProcessingJobDetailResponse, ProcessingJobListResponse,
    ProcessingStatsResponse, QueueMetrics, WorkerHealthResponse,
)
from apps.api.redis_client import redis_health_check, get_redis
from apps.api.config import settings

router = APIRouter(prefix="/jobs", tags=["Processing Jobs"])


@router.get("", response_model=ProcessingJobListResponse)
def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    document_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ProcessingJob)
    if status:
        query = query.filter(ProcessingJob.status == status)
    if document_id:
        query = query.filter(ProcessingJob.document_id == document_id)

    total = query.count()
    jobs = query.order_by(desc(ProcessingJob.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return ProcessingJobListResponse(
        items=jobs, total=total, page=page, page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{job_id}", response_model=ProcessingJobDetailResponse)
def get_job(job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/{job_id}/retry", response_model=ProcessingJobResponse)
def retry_job(job_id: str, current_user: User = Depends(require_engineer_or_admin), db: Session = Depends(get_db)):
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.failed:
        raise HTTPException(400, "Only failed jobs can be retried")
    if job.retry_count >= job.max_retries:
        raise HTTPException(400, "Job has exceeded its maximum retry count")

    doc = db.query(Document).filter(Document.id == job.document_id).first()
    if not doc:
        raise HTTPException(404, "Associated document not found")

    from apps.api.routers.documents import get_minio_client
    try:
        minio = get_minio_client()
        obj = minio.get_object(settings.MINIO_BUCKET, doc.filename)
        file_bytes = obj.read()
    except Exception as e:
        raise HTTPException(500, f"Could not retrieve file from storage: {e}")

    job.retry_count += 1
    job.status = JobStatus.queued
    job.error_message = None
    db.commit()

    from apps.api.workers.document_tasks import queue_document_pipeline
    queue_document_pipeline(job.id, doc.id, file_bytes, doc.mime_type, doc.original_filename)

    db.refresh(job)
    return job


@router.post("/{job_id}/cancel", response_model=ProcessingJobResponse)
def cancel_job_endpoint(job_id: str, current_user: User = Depends(require_engineer_or_admin), db: Session = Depends(get_db)):
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status in (JobStatus.completed, JobStatus.cancelled, JobStatus.failed):
        raise HTTPException(400, f"Cannot cancel a job in status '{job.status.value}'")

    from apps.api.workers.celery_app import celery_app
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=False)
    job.status = JobStatus.cancelled
    db.commit()
    db.refresh(job)
    return job


@router.get("/stats/overview", response_model=ProcessingStatsResponse)
def processing_stats(current_user: User = Depends(require_engineer_or_admin), db: Session = Depends(get_db)):
    running = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.processing).count()
    completed = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.completed).count()
    failed = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.failed).count()
    retry_queue = db.query(ProcessingJob).filter(
        ProcessingJob.status == JobStatus.failed, ProcessingJob.retry_count < ProcessingJob.max_retries
    ).count()
    avg_duration = db.query(sqlfunc.avg(ProcessingJob.duration_seconds)).filter(
        ProcessingJob.status == JobStatus.completed
    ).scalar() or 0.0

    redis_status = redis_health_check()

    queues = []
    try:
        from apps.api.workers.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=1.0)
        active = inspect.active() or {}
        scheduled = inspect.scheduled() or {}
        reserved = inspect.reserved() or {}
        for queue_name in ("documents", "ocr", "embedding", "cleanup"):
            active_count = sum(len(v) for v in active.values())
            scheduled_count = sum(len(v) for v in scheduled.values())
            reserved_count = sum(len(v) for v in reserved.values())
            queues.append(QueueMetrics(
                queue_name=queue_name,
                pending=db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.queued).count(),
                active=active_count, scheduled=scheduled_count, reserved=reserved_count,
            ))
    except Exception:
        pass  # workers offline; dashboard shows DB-derived stats only

    workers = [
        WorkerHealthResponse(
            worker_name=w.worker_name, status=w.status, active_tasks=w.active_tasks,
            processed_tasks=w.processed_tasks, concurrency=w.concurrency, last_heartbeat=w.last_heartbeat,
        )
        for w in db.query(WorkerStatus).all()
    ]

    return ProcessingStatsResponse(
        running_jobs=running, completed_jobs=completed, failed_jobs=failed, retry_queue=retry_queue,
        avg_processing_time_seconds=round(float(avg_duration), 2), redis=redis_status,
        queues=queues, workers=workers,
    )
