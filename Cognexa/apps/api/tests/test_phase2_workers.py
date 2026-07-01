"""
Phase 2 tests — Celery config sanity, audit service, Redis client construction.
These are unit-level tests that don't require a live Redis/Postgres connection
(broker/backend objects are constructed but not connected to during import).
"""
import pytest


class TestCeleryConfig:
    def test_celery_app_imports(self):
        from apps.api.workers.celery_app import celery_app
        assert celery_app.main == "indusmind"

    def test_task_routes_configured(self):
        from apps.api.workers.celery_app import celery_app
        routes = celery_app.conf.task_routes
        assert "apps.api.workers.ocr_tasks.*" in routes
        assert routes["apps.api.workers.ocr_tasks.*"]["queue"] == "ocr"
        assert routes["apps.api.workers.embedding_tasks.*"]["queue"] == "embedding"

    def test_retry_and_time_limits_configured(self):
        from apps.api.workers.celery_app import celery_app
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.task_soft_time_limit > 0
        assert celery_app.conf.task_time_limit >= celery_app.conf.task_soft_time_limit

    def test_beat_schedule_has_cleanup_jobs(self):
        from apps.api.workers.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "cleanup-temp-files-hourly" in schedule
        assert "recover-failed-jobs-every-15-min" in schedule
        assert "purge-old-failed-jobs-daily" in schedule


class TestAuditService:
    def test_classify_action_upload(self):
        from apps.api.services.audit import classify_action
        assert classify_action("POST", "/api/v1/documents/upload") == "upload"

    def test_classify_action_delete(self):
        from apps.api.services.audit import classify_action
        assert classify_action("DELETE", "/api/v1/documents/abc123") == "delete"

    def test_classify_action_download(self):
        from apps.api.services.audit import classify_action
        assert classify_action("GET", "/api/v1/documents/abc123/download") == "download"

    def test_classify_action_unmapped_returns_none(self):
        from apps.api.services.audit import classify_action
        assert classify_action("GET", "/api/v1/dashboard/stats") is None

    def test_write_audit_log_falls_back_on_unknown_action(self, db_session):
        from apps.api.services.audit import write_audit_log
        entry = write_audit_log(db_session, action="not_a_real_action", status="success")
        assert entry.action.value == "api_error"
        assert "not_a_real_action" in (entry.detail or "")


class TestRedisClient:
    def test_get_redis_pool_is_singleton(self):
        from apps.api.redis_client import get_redis_pool
        pool1 = get_redis_pool()
        pool2 = get_redis_pool()
        assert pool1 is pool2


@pytest.fixture
def db_session():
    """In-memory SQLite session for lightweight model/service tests."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from apps.api.db import Base
    import apps.api.models  # noqa: F401 ensures all models are registered

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
