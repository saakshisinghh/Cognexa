from __future__ import annotations

import csv
import io
import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.models import AuditLog, User
from apps.api.routers.auth import require_admin
from apps.api.schemas.audit import AuditLogResponse, AuditLogListResponse

router = APIRouter(prefix="/audit", tags=["Audit"])


def _apply_filters(
    query,
    action: Optional[str],
    status: Optional[str],
    user_id: Optional[str],
    resource: Optional[str],
    search: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
):
    if action:
        query = query.filter(AuditLog.action == action)
    if status:
        query = query.filter(AuditLog.status == status)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if resource:
        query = query.filter(AuditLog.resource.ilike(f"%{resource}%"))
    if search:
        query = query.filter(
            (AuditLog.user_email.ilike(f"%{search}%")) |
            (AuditLog.resource.ilike(f"%{search}%")) |
            (AuditLog.detail.ilike(f"%{search}%"))
        )
    if date_from:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.filter(AuditLog.timestamp <= date_to)
    return query


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    sort_order: str = "desc",
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = _apply_filters(db.query(AuditLog), action, status, user_id, resource, search, date_from, date_to)
    total = query.count()
    query = query.order_by(desc(AuditLog.timestamp) if sort_order == "desc" else asc(AuditLog.timestamp))
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return AuditLogListResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/export.csv")
def export_audit_logs_csv(
    action: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = _apply_filters(db.query(AuditLog), action, status, user_id, resource, search, date_from, date_to)
    rows = query.order_by(desc(AuditLog.timestamp)).limit(50000).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timestamp", "user_email", "role", "ip_address", "resource", "action",
        "status", "duration_ms", "correlation_id", "detail",
    ])
    for r in rows:
        writer.writerow([
            r.timestamp.isoformat() if r.timestamp else "", r.user_email or "", r.role or "",
            r.ip_address or "", r.resource or "", r.action.value, r.status.value,
            r.duration_ms or "", r.correlation_id or "", r.detail or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


@router.get("/export.json")
def export_audit_logs_json(
    action: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = _apply_filters(db.query(AuditLog), action, status, user_id, resource, search, date_from, date_to)
    rows = query.order_by(desc(AuditLog.timestamp)).limit(50000).all()
    return [AuditLogResponse.model_validate(r).model_dump(mode="json") for r in rows]
