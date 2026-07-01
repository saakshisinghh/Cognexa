"""
Audit Service — writes structured AuditLog rows.

Used three ways:
  1. `audit_middleware` in main.py — automatically logs every mutating
     request (upload/delete/rename/search/etc.) with timing + correlation id.
  2. Explicit calls from routers for events middleware can't infer
     (e.g. login/logout/role_change carry semantics the URL alone can't give).
  3. Worker tasks (via workers/_helpers.write_audit_event) for async events.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from apps.api.models import AuditLog, AuditAction, AuditStatus

logger = logging.getLogger("indusmind.audit")


def write_audit_log(
    db: Session,
    *,
    action: str,
    status: str = "success",
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    role: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    resource: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    duration_ms: Optional[float] = None,
    correlation_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> AuditLog:
    try:
        action_enum = AuditAction(action)
    except ValueError:
        action_enum = AuditAction.api_error
        detail = f"(unmapped action '{action}') {detail or ''}".strip()

    try:
        status_enum = AuditStatus(status)
    except ValueError:
        status_enum = AuditStatus.success

    entry = AuditLog(
        action=action_enum,
        status=status_enum,
        user_id=user_id,
        user_email=user_email,
        role=role,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=resource,
        old_value=old_value,
        new_value=new_value,
        duration_ms=duration_ms,
        correlation_id=correlation_id,
        detail=detail,
    )
    db.add(entry)
    db.flush()
    return entry


# Maps (method, path-prefix) -> AuditAction for the automatic request middleware.
# Only mutating / sensitive read endpoints are logged automatically; everything
# else (health checks, static assets) is skipped for noise reduction.
ROUTE_ACTION_MAP = [
    ("POST", "/api/v1/documents/upload", "upload"),
    ("POST", "/api/v1/documents/bulk-upload", "upload"),
    ("DELETE", "/api/v1/documents/", "delete"),
    ("PATCH", "/api/v1/documents/", "rename"),
    ("GET", "/api/v1/documents/", "download"),  # narrowed further to /download suffix in middleware
    ("POST", "/api/v1/documents/", "reprocess"),  # /{id}/reprocess
    ("GET", "/api/v1/search", "search"),
    ("POST", "/api/v1/copilot", "chat_query"),
    ("PATCH", "/api/v1/assets/", "asset_update"),
    ("PUT", "/api/v1/assets/", "asset_update"),
]


def classify_action(method: str, path: str) -> Optional[str]:
    if path.endswith("/download"):
        return "download"
    if path.endswith("/reprocess"):
        return "reprocess"
    if path.startswith("/api/v1/documents/upload") or path.startswith("/api/v1/documents/bulk-upload"):
        return "upload"
    if path.startswith("/api/v1/documents/") and method == "DELETE":
        return "delete"
    if path.startswith("/api/v1/documents/") and method == "PATCH":
        return "rename"
    if path.startswith("/api/v1/search"):
        return "search"
    if path.startswith("/api/v1/copilot"):
        return "chat_query"
    if path.startswith("/api/v1/assets/") and method in ("PATCH", "PUT"):
        return "asset_update"
    if path.startswith("/api/v1/auth/me") and method == "PATCH":
        return "settings_change"
    return None
