from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Index,
    func,
)
from sqlalchemy.orm import relationship

from apps.api.db import Base


def generate_uuid():
    return str(uuid.uuid4())


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Incident(Base):
    __tablename__ = "incidents"

    __table_args__ = (
        Index("ix_incidents_asset_id_occurred_at", "asset_id", "occurred_at"),
    )

    # Primary Key (String to match existing models)
    id = Column(String, primary_key=True, default=generate_uuid)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # Foreign Keys (String to match existing users/assets/documents tables)
    asset_id = Column(
        String,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )

    document_id = Column(
        String,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    reported_by = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    severity = Column(
        SAEnum(IncidentSeverity),
        nullable=False,
        default=IncidentSeverity.MEDIUM,
    )

    status = Column(
        SAEnum(IncidentStatus),
        nullable=False,
        default=IncidentStatus.OPEN,
    )

    failure_mode_code = Column(String(20), nullable=True)

    occurred_at = Column(DateTime(timezone=True), nullable=False)

    graph_synced_at = Column(DateTime(timezone=True), nullable=True)

    graph_sync_status = Column(
        String(20),
        nullable=False,
        default="pending",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    asset = relationship("Asset", backref="incidents")

    def __repr__(self):
        return (
            f"<Incident id={self.id} "
            f"asset_id={self.asset_id} "
            f"severity={self.severity}>"
        )