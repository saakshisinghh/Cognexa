"""
Shared helpers used across worker task modules.
Kept separate from celery_app.py to avoid circular imports
(task modules import celery_app; celery_app.include's the task modules).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from apps.api.db import SessionLocal
from apps.api.models import ProcessingJob, TaskExecution, TaskMetrics, JobStatus, JobStep, TaskState

logger = logging.getLogger("indusmind.workers")


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_job(
    db,
    job_id: str,
    *,
    status: Optional[JobStatus] = None,
    step: Optional[JobStep] = None,
    progress: Optional[int] = None,
    error: Optional[str] = None,
    celery_task_id: Optional[str] = None,
) -> Optional[ProcessingJob]:
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job:
        logger.warning(f"ProcessingJob {job_id} not found for update")
        return None

    now = datetime.now(timezone.utc)
    if status is not None:
        job.status = status
        if status == JobStatus.processing and job.started_at is None:
            job.started_at = now
        if status in (JobStatus.completed, JobStatus.failed, JobStatus.cancelled):
            job.completed_at = now
            if job.started_at:
                job.duration_seconds = (now - job.started_at).total_seconds()
    if step is not None:
        job.current_step = step
    if progress is not None:
        job.progress_percent = max(0, min(100, progress))
    if error is not None:
        job.error_message = error
    if celery_task_id is not None:
        job.celery_task_id = celery_task_id

    db.flush()
    return job


def record_task_execution(
    db,
    job_id: str,
    celery_task_id: str,
    task_name: str,
    queue: str,
    state: TaskState,
    attempt: int = 1,
    result=None,
    error: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> TaskExecution:
    existing = (
        db.query(TaskExecution)
        .filter(TaskExecution.celery_task_id == celery_task_id)
        .first()
    )
    if existing:
        te = existing
    else:
        te = TaskExecution(
            job_id=job_id,
            celery_task_id=celery_task_id,
            task_name=task_name,
            queue=queue,
            attempt=attempt,
        )
        db.add(te)

    te.state = state
    if result is not None:
        te.result = result
    if error is not None:
        te.error_message = error
    if started_at is not None:
        te.started_at = started_at
    if finished_at is not None:
        te.finished_at = finished_at
        if te.started_at:
            te.duration_seconds = (finished_at - te.started_at).total_seconds()

    db.flush()
    update_task_metrics(db, task_name, state, te.duration_seconds)
    return te


def update_task_metrics(db, task_name: str, state: TaskState, duration_seconds: Optional[float]):
    metrics = db.query(TaskMetrics).filter(TaskMetrics.task_name == task_name).first()
    if not metrics:
        metrics = TaskMetrics(task_name=task_name)
        db.add(metrics)
        db.flush()

    if state == TaskState.success:
        metrics.total_success += 1
        metrics.total_runs += 1
    elif state == TaskState.failure:
        metrics.total_failure += 1
        metrics.total_runs += 1
    elif state == TaskState.retry:
        metrics.total_retries += 1

    if duration_seconds is not None and state == TaskState.success:
        n = metrics.total_success
        prev_avg = metrics.avg_duration_seconds or 0.0
        metrics.avg_duration_seconds = ((prev_avg * (n - 1)) + duration_seconds) / n if n > 0 else duration_seconds

    metrics.last_run_at = datetime.now(timezone.utc)
    db.flush()


def write_audit_event(
    *,
    action: str,
    status: str = "success",
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    detail: Optional[str] = None,
    old_value=None,
    new_value=None,
):
    """Fire-and-forget audit log write from within a worker (own DB session)."""
    try:
        from apps.api.services.audit import write_audit_log
        with session_scope() as db:
            write_audit_log(
                db,
                action=action,
                status=status,
                user_id=user_id,
                resource=resource,
                detail=detail,
                old_value=old_value,
                new_value=new_value,
            )
    except Exception as e:
        logger.warning(f"Failed to write audit event from worker: {e}")
