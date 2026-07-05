"""
apps/api/workers/celery_app.py

FIX: Added apps.api.pipelines.graph_sync to the `include` list.
Phase 3 graph sync Celery tasks use @shared_task which means Celery must
discover the module at startup. Without this, sync_incident_task.delay()
raises celery.exceptions.NotRegistered at runtime.

Also added a `graph` queue to beat_schedule and task_routes.
Everything else is unchanged from Phase 2.
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
        # FIX: Phase 3 graph sync tasks — must be registered here
        "apps.api.pipelines.graph_sync",
    ],
)

celery_app.conf.update(
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    task_routes={
        "apps.api.workers.ocr_tasks.*": {"queue": "ocr"},
        "apps.api.workers.embedding_tasks.*": {"queue": "embedding"},
        "apps.api.workers.document_tasks.*": {"queue": "documents"},
        "apps.api.workers.cleanup_tasks.*": {"queue": "cleanup"},
        # FIX: graph tasks routed to their own queue
        "graph.*": {"queue": "graph"},
    },
    task_queues=None,

    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_transport_options={
        "visibility_timeout": 3600,
        "max_retries": 10,
    },
    result_expires=settings.CELERY_RESULT_EXPIRES,
    result_extended=True,

    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,

    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    task_default_priority=5,
    worker_send_task_events=True,
    task_send_sent_event=True,

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
    # FIX: Phase 3 — nightly similarity computation
    "compute-asset-similarity-nightly": {
        "task": "graph.compute_asset_similarity",
        "schedule": 86400.0,
    },
}


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