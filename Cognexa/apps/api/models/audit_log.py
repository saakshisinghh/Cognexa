"""
Phase 2 models — Audit Logging & Asynchronous Processing.

Kept in a dedicated module (per spec) and re-exported from
`apps.api.models` so they register on the same `Base` / metadata and
get created by `Base.metadata.create_all()` in main.py's lifespan,
exactly like the Phase 1 models.
"""
from __future__ import annotations
import enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Enum, JSON, BigInteger, Index, func
)
from sqlalchemy.orm import relationship

from apps.api.db import Base


def generate_uuid():
    return str(uuid.uuid4())


# ─── Enums ──────────────────────────────────────────────────────────────────

class AuditAction(str, enum.Enum):
    login = "login"
    logout = "logout"
    login_failed = "login_failed"
    upload = "upload"
    delete = "delete"
    rename = "rename"
    update = "update"
    search = "search"
    chat_query = "chat_query"
    download = "download"
    role_change = "role_change"
    asset_update = "asset_update"
    settings_change = "settings_change"
    api_error = "api_error"
    auth_failure = "auth_failure"
    reprocess = "reprocess"
    retry_task = "retry_task"
    cancel_task = "cancel_task"
    # ─ Phase 5: Agentic AI Platform ─
    agent_execute = "agent_execute"
    agent_cancel = "agent_cancel"
    agent_enable = "agent_enable"
    agent_disable = "agent_disable"
    workflow_execute = "workflow_execute"


class AuditStatus(str, enum.Enum):
    success = "success"
    failure = "failure"
    denied = "denied"


class JobStatus(str, enum.Enum):
    pending = "pending"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobStep(str, enum.Enum):
    created = "created"
    ocr = "ocr"
    entity_extraction = "entity_extraction"
    chunking = "chunking"
    embedding = "embedding"
    vector_storage = "vector_storage"
    finalizing = "finalizing"
    done = "done"


class TaskState(str, enum.Enum):
    pending = "pending"
    started = "started"
    retry = "retry"
    success = "success"
    failure = "failure"
    revoked = "revoked"


# ─── Audit ──────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_email = Column(String, nullable=True)
    role = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    resource = Column(String, nullable=True, index=True)   # e.g. "document:<id>"
    action = Column(Enum(AuditAction), nullable=False, index=True)
    status = Column(Enum(AuditStatus), default=AuditStatus.success, nullable=False, index=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    duration_ms = Column(Float, nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    detail = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_user_timestamp", "user_id", "timestamp"),
        Index("ix_audit_logs_action_timestamp", "action", "timestamp"),
    )


# ─── Async processing jobs ───────────────────────────────────────────────────

class ProcessingJob(Base):
    """One row per document-processing pipeline run (created at upload time)."""
    __tablename__ = "processing_jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False, index=True)
    current_step = Column(Enum(JobStep), default=JobStep.created, nullable=False)
    progress_percent = Column(Integer, default=0, nullable=False)
    celery_task_id = Column(String, nullable=True, index=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    document = relationship("Document")
    tasks = relationship("TaskExecution", back_populates="job", cascade="all, delete-orphan")


class TaskExecution(Base):
    """Individual Celery task execution belonging to a ProcessingJob."""
    __tablename__ = "task_executions"

    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    celery_task_id = Column(String, nullable=False, index=True)
    task_name = Column(String, nullable=False)
    queue = Column(String, default="default")
    state = Column(Enum(TaskState), default=TaskState.pending, nullable=False, index=True)
    attempt = Column(Integer, default=1, nullable=False)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("ProcessingJob", back_populates="tasks")


class TaskMetrics(Base):
    """Rolling aggregate metrics per task name, updated by workers."""
    __tablename__ = "task_metrics"

    id = Column(String, primary_key=True, default=generate_uuid)
    task_name = Column(String, nullable=False, unique=True, index=True)
    total_runs = Column(Integer, default=0, nullable=False)
    total_success = Column(Integer, default=0, nullable=False)
    total_failure = Column(Integer, default=0, nullable=False)
    total_retries = Column(Integer, default=0, nullable=False)
    avg_duration_seconds = Column(Float, default=0.0, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkerStatus(Base):
    """Heartbeat row per Celery worker, upserted by a periodic beat task."""
    __tablename__ = "worker_status"

    id = Column(String, primary_key=True, default=generate_uuid)
    worker_name = Column(String, nullable=False, unique=True, index=True)
    hostname = Column(String, nullable=True)
    status = Column(String, default="unknown")   # online | offline | unknown
    active_tasks = Column(Integer, default=0)
    processed_tasks = Column(BigInteger, default=0)
    concurrency = Column(Integer, default=0)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class QueueStatistics(Base):
    """Periodic snapshot of queue depth / throughput, written by Celery beat."""
    __tablename__ = "queue_statistics"

    id = Column(String, primary_key=True, default=generate_uuid)
    queue_name = Column(String, nullable=False, index=True)
    pending_count = Column(Integer, default=0)
    processing_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    avg_wait_seconds = Column(Float, default=0.0)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
