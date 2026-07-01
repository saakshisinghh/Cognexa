from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class TaskExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    celery_task_id: str
    task_name: str
    queue: str
    state: str
    attempt: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class ProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    status: str
    current_step: str
    progress_percent: int
    celery_task_id: Optional[str] = None
    retry_count: int
    max_retries: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class ProcessingJobDetailResponse(ProcessingJobResponse):
    tasks: List[TaskExecutionResponse] = []


class ProcessingJobListResponse(BaseModel):
    items: List[ProcessingJobResponse]
    total: int
    page: int
    page_size: int
    pages: int


class QueueMetrics(BaseModel):
    queue_name: str
    pending: int
    active: int
    scheduled: int
    reserved: int


class WorkerHealthResponse(BaseModel):
    worker_name: str
    status: str
    active_tasks: int
    processed_tasks: int
    concurrency: int
    last_heartbeat: Optional[datetime] = None


class ProcessingStatsResponse(BaseModel):
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    retry_queue: int
    avg_processing_time_seconds: float
    redis: dict
    queues: List[QueueMetrics]
    workers: List[WorkerHealthResponse]
