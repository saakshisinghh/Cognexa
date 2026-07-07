"""
INDUS MIND API — FastAPI application entrypoint.
Production-grade monolith for Phase 1 + Phase 2 (async processing & audit).
"""
from __future__ import annotations
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc, text

from apps.api.config import settings
from apps.api.db import engine, get_db, SessionLocal
from apps.api.models import Base, Document, Asset, User, Conversation, DocumentStatus

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("indusmind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    try:
        from apps.api.services.agent_registry import sync_agent_definitions
        registry_db = SessionLocal()
        try:
            sync_agent_definitions(registry_db)
            logger.info("Phase 5 agent registry synced")
        finally:
            registry_db.close()
    except Exception as e:
        logger.warning(f"Agent registry sync failed (non-fatal): {e}")

    try:
        from apps.api.seed import run_startup_seed
        seed_db = SessionLocal()
        try:
            run_startup_seed(seed_db)
        finally:
            seed_db.close()
    except Exception as e:
        logger.error(f"Startup seeding failed (non-fatal): {e}")

    try:
        from apps.api.weaviate_client import get_weaviate_client, ensure_schema
        wv_client = get_weaviate_client()
        ensure_schema(wv_client)
        logger.info("Weaviate schema initialized")
    except Exception as e:
        logger.warning(f"Weaviate initialization failed (non-fatal): {e}")

    try:
        from apps.api.services.embedder import embed_texts
        embed_texts(["warmup"])
        logger.info("Embedding model warmed up")
    except Exception as e:
        logger.warning(f"Embedding warmup failed: {e}")

    try:
        from apps.api.redis_client import get_redis
        get_redis().ping()
        logger.info("Redis connection verified")
    except Exception as e:
        logger.warning(f"Redis check failed (Celery features degraded): {e}")

    logger.info("INDUS MIND API ready")
    yield

    try:
        from apps.api.weaviate_client import close_weaviate_client
        close_weaviate_client()
    except Exception:
        pass
    try:
        from apps.api.redis_client import close_redis_pool
        close_redis_pool()
    except Exception:
        pass
    logger.info("INDUS MIND API shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="The Operating Memory of Industrial Enterprises — Phase 1 MVP API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    duration = round((time.time() - start) * 1000, 2)
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration}ms)")
    response.headers["X-Response-Time"] = f"{duration}ms"
    return response


@app.middleware("http")
async def audit_and_correlation_middleware(request: Request, call_next):
    """
    Phase 2: stamps every request with a correlation ID (propagated to clients
    via X-Correlation-ID and available to routers/workers via request.state),
    and automatically writes an AuditLog row for mutating/sensitive endpoints
    classified in services/audit.classify_action. Explicit audit calls inside
    routers (login, role_change, etc.) take precedence and are not duplicated
    here since those actions aren't in the classification map.
    """
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    start = time.time()

    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    response.headers["X-Correlation-ID"] = correlation_id

    action = None
    try:
        from apps.api.services.audit import classify_action
        action = classify_action(request.method, request.url.path)
    except Exception:
        pass

    if action:
        try:
            from apps.api.services.audit import write_audit_log
            user_id = None
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                try:
                    from apps.api.routers.auth import decode_access_token
                    payload = decode_access_token(auth_header.split(" ", 1)[1])
                    user_id = payload.get("sub")
                except Exception:
                    user_id = None
            db = SessionLocal()
            try:
                write_audit_log(
                    db,
                    action=action,
                    status="success" if response.status_code < 400 else "failure",
                    user_id=user_id,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    resource=request.url.path,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                    detail=f"{request.method} {request.url.path} -> {response.status_code}",
                )
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Audit middleware failed to write log: {e}")

    return response


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database error on {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Database error occurred"})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


from apps.api.routers import auth, documents, search, copilot, assets, audit, jobs, graph, incidents, agents

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(copilot.router, prefix="/api/v1")
app.include_router(assets.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(graph.router, prefix="/api/v1/graph", tags=["Knowledge Graph"])
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["Incidents"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])


@app.get("/api/health", tags=["Health"])
async def health_check():
    services = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception as e:
        services["database"] = f"error: {str(e)}"

    try:
        from apps.api.weaviate_client import get_weaviate_client
        client = get_weaviate_client()
        client.is_ready()
        services["weaviate"] = "ok"
    except Exception as e:
        services["weaviate"] = f"error: {str(e)}"

    try:
        from minio import Minio
        mc = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        mc.list_buckets()
        services["minio"] = "ok"
    except Exception as e:
        services["minio"] = f"error: {str(e)}"

    try:
        from apps.api.redis_client import redis_health_check
        redis_status = redis_health_check()
        services["redis"] = redis_status.get("status", "error")
    except Exception as e:
        services["redis"] = f"error: {str(e)}"

    try:
        from apps.api.workers.celery_app import celery_app
        ping = celery_app.control.ping(timeout=1.0)
        services["celery_workers"] = "ok" if ping else "no_workers_online"
    except Exception as e:
        services["celery_workers"] = f"error: {str(e)}"

    all_ok = all(v == "ok" for v in services.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "services": services,
    }


@app.get("/api/v1/dashboard/stats", tags=["Dashboard"])
async def get_dashboard_stats(
    current_user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    total_documents = db.query(Document).count()
    total_assets = db.query(Asset).count()
    total_users = db.query(User).count()
    total_conversations = db.query(Conversation).count()
    docs_processing = db.query(Document).filter(Document.status == DocumentStatus.processing).count()
    docs_completed = db.query(Document).filter(Document.status == DocumentStatus.completed).count()
    docs_failed = db.query(Document).filter(Document.status == DocumentStatus.failed).count()
    storage_used = db.query(sqlfunc.sum(Document.file_size)).scalar() or 0

    recent_docs = (
        db.query(Document)
        .order_by(Document.created_at.desc())
        .limit(5)
        .all()
    )
    recent_convos = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(5)
        .all()
    )

    return {
        "total_documents": total_documents,
        "total_assets": total_assets,
        "total_users": total_users,
        "total_conversations": total_conversations,
        "documents_processing": docs_processing,
        "documents_completed": docs_completed,
        "documents_failed": docs_failed,
        "storage_used_bytes": storage_used,
        "recent_uploads": [
            {
                "id": d.id,
                "filename": d.original_filename,
                "status": d.status.value,
                "created_at": d.created_at.isoformat(),
            }
            for d in recent_docs
        ],
        "recent_conversations": [
            {
                "id": c.id,
                "title": c.title,
                "updated_at": c.updated_at.isoformat(),
            }
            for c in recent_convos
        ],
    }