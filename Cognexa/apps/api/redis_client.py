"""
Redis Client — Phase 2.

Provides a process-wide connection pool used by:
  - FastAPI app (health checks, queue/worker metrics)
  - Celery broker/result backend (configured separately in workers/celery_app.py,
    but reuses the same connection parameters)

Design notes:
  - A single `redis.ConnectionPool` is created lazily and reused across requests.
  - `retry_on_timeout` + `health_check_interval` let the underlying client
    detect dead connections and transparently reconnect.
  - `get_redis()` is safe to call from sync code (routers, services); for
    Celery tasks use `get_redis()` as well since tasks run in worker processes
    with their own pool instance.
"""
from __future__ import annotations

import logging
from typing import Optional

import redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

from apps.api.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[redis.ConnectionPool] = None


def get_redis_pool() -> redis.ConnectionPool:
    global _pool
    if _pool is None:
        retry = Retry(ExponentialBackoff(cap=10, base=0.5), retries=5)
        _pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_keepalive=True,
            retry_on_timeout=settings.REDIS_RETRY_ON_TIMEOUT,
            retry=retry,
            health_check_interval=settings.REDIS_HEALTH_CHECK_INTERVAL,
            decode_responses=True,
        )
        logger.info("Redis connection pool initialized")
    return _pool


def get_redis() -> redis.Redis:
    """Return a Redis client backed by the shared connection pool."""
    return redis.Redis(connection_pool=get_redis_pool())


def redis_health_check() -> dict:
    """Used by /api/health and the worker/queue dashboard."""
    try:
        client = get_redis()
        latency_ms = None
        import time

        start = time.time()
        pong = client.ping()
        latency_ms = round((time.time() - start) * 1000, 2)
        info = client.info(section="memory")
        return {
            "status": "ok" if pong else "error",
            "latency_ms": latency_ms,
            "used_memory_human": info.get("used_memory_human"),
            "max_connections": settings.REDIS_MAX_CONNECTIONS,
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "error", "error": str(e)}


def close_redis_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.disconnect()
        except Exception:
            pass
        _pool = None
        logger.info("Redis connection pool closed")
