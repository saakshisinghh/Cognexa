from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    role: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource: Optional[str] = None
    action: str
    status: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    duration_ms: Optional[float] = None
    correlation_id: Optional[str] = None
    detail: Optional[str] = None


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    pages: int
