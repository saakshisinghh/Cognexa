"""
apps/api/models/query_history.py


"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB


from sqlalchemy.orm import relationship

from apps.api.db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class QueryHistory(Base):
    __tablename__ = "query_history"

    # ── Phase 1 base columns ────────────────────────────────────────────────
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=True)
    retrieved_chunks = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Phase 4 columns (added by migrations/versions/conversation_sessions.py) ─
    session_id = Column(
            String,
        ForeignKey("conversation_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence_level = Column(String(10), nullable=True)  # "high" | "medium" | "low"
    confidence_score = Column(Numeric(precision=6, scale=4), nullable=True)
    conflict_detected = Column(Boolean, nullable=True)
    conflict_count = Column(Integer, nullable=True)
    conflicts_json = Column(Text, nullable=True)
    retrieval_stats_json = Column(Text, nullable=True)
    feedback = Column(String(10), nullable=True)  # "positive" | "negative" | NULL
    elapsed_ms = Column(Integer, nullable=True)

    user = relationship("User", backref="query_history_entries")