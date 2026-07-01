"""
Celery Application — Phase 2.

Production configuration covering:
  - Redis broker + result backend (separate DB indices, see config.py)
  - Task routing into dedicated queues
  - Exponential-backoff retries with jitter, capped max backoff
  - Worker concurrency / prefetch tuned for IO + CPU bound mixed workloads
  - Soft/hard time limits so a stuck task can't wedge a worker forever
  - Dead-letter strategy: tasks that exhaust retries are marked `failed` on the
    ProcessingJob/TaskExecution rows (see workers/document_tasks.py on_failure)
    instead of being silently dropped — the `failed` queue acts as the DLQ view
    via the Processing Dashboard / Retry API rather than a separate broker queue.
  - Graceful shutdown via Celery's own worker_shutdown signal (logged for ops).
"""
from __future__ import annotations

import logging

from celery import Celery
from celery.signals import (
    worker_ready, worker_shutdown, task_prerun, task_postrun, task_failure, task_retry,
)

from apps.api.config import settings

logger = logging.getLogger("indusmind.celery")

celery_app = Celery(
    "indusmind",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "apps.api.workers.document_tasks",
        "apps.api.workers.ocr_tasks",
        "apps.api.workers.embedding_tasks",
        "apps.api.workers.cleanup_tasks",
    ],
)

celery_app.conf.update(
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    task_routes={
        "apps.api.workers.ocr_tasks.*": {"queue": "ocr"},
        "apps.api.workers.embedding_tasks.*": {"queue": "embedding"},
        "apps.api.workers.document_tasks.*": {"queue": "documents"},
        "apps.api.workers.cleanup_tasks.*": {"queue": "cleanup"},
    },
    task_queues=None,  # let Celery auto-create the queues referenced above

    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,                 # ack only after task completes -> safe redelivery on worker crash
    worker_prefetch_multiplier=1,        # don't hoard tasks; fair dispatch across workers
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_transport_options={
        "visibility_timeout": 3600,
        "max_retries": 10,
    },
    result_expires=settings.CELERY_RESULT_EXPIRES,
    result_extended=True,

    # Time limits (graceful soft limit raises SoftTimeLimitExceeded for cleanup,
    # hard limit kills the worker process as last resort)
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,

    # Concurrency / priority
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    task_default_priority=5,
    worker_send_task_events=True,         # enables monitoring (flower / events)
    task_send_sent_event=True,

    # Retries (defaults; individual tasks override via autoretry_for / retry_backoff)
    task_default_retry_delay=settings.CELERY_TASK_RETRY_BACKOFF,
)

celery_app.conf.beat_schedule = {
    "cleanup-temp-files-hourly": {
        "task": "apps.api.workers.cleanup_tasks.cleanup_temp_files",
        "schedule": 3600.0,
    },
    "recover-failed-jobs-every-15-min": {
        "task": "apps.api.workers.cleanup_tasks.recover_stuck_jobs",
        "schedule": 900.0,
    },
    "purge-old-failed-jobs-daily": {
        "task": "apps.api.workers.cleanup_tasks.purge_old_failed_jobs",
        "schedule": 86400.0,
    },
    "record-queue-statistics-minutely": {
        "task": "apps.api.workers.cleanup_tasks.record_queue_statistics",
        "schedule": 60.0,
    },
    "record-worker-heartbeats-every-30s": {
        "task": "apps.api.workers.cleanup_tasks.record_worker_heartbeats",
        "schedule": 30.0,
    },
}


# ─── Monitoring / lifecycle hooks ────────────────────────────────────────────

@worker_ready.connect
def _on_worker_ready(sender=None, **kwargs):
    logger.info(f"Celery worker ready: {getattr(sender, 'hostname', 'unknown')}")


@worker_shutdown.connect
def _on_worker_shutdown(sender=None, **kwargs):
    logger.info(f"Celery worker shutting down gracefully: {getattr(sender, 'hostname', 'unknown')}")


@task_prerun.connect
def _on_task_prerun(task_id=None, task=None, **kwargs):
    logger.info(f"[task start] {task.name if task else '?'} id={task_id}")


@task_postrun.connect
def _on_task_postrun(task_id=None, task=None, state=None, **kwargs):
    logger.info(f"[task end] {task.name if task else '?'} id={task_id} state={state}")


@task_failure.connect
def _on_task_failure(task_id=None, exception=None, **kwargs):
    logger.error(f"[task failure] id={task_id} error={exception}")


@task_retry.connect
def _on_task_retry(request=None, reason=None, **kwargs):
    logger.warning(f"[task retry] id={getattr(request, 'id', '?')} reason={reason}")