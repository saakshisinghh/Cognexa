"""
apps/api/models/knowledge_gap.py

Phase 6 — Knowledge Gap Detection.

One row per asset (not per category) — recomputed nightly by
workers/gap_tasks.py::compute_knowledge_gaps_task. missing_categories /
present_categories / expected_categories are stored as JSON snapshots of
what was evaluated at compute time, so a dashboard can show the detail
breakdown without a second query, and so changes to the expected-category
weighting over time (see services/gap.py) don't silently reinterpret old
rows.

This is a brand-new table — unlike Phase 6 Feature 1's changes to the
existing chunks/documents tables, Base.metadata.create_all() (called at
API boot) WILL create this table automatically the next time the API
starts, since it does not exist yet. No manual ALTER TABLE needed.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey, func, CheckConstraint

from apps.api.db import Base


def generate_uuid():
    return str(uuid.uuid4())


class AssetKnowledgeGap(Base):
    __tablename__ = "asset_knowledge_gaps"
    __table_args__ = (
        CheckConstraint("gap_score >= 0.0 AND gap_score <= 1.0", name="ck_asset_knowledge_gap_score_range"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    gap_score = Column(Float, nullable=False, default=0.0)  # 0.0 = fully documented, 1.0 = fully undocumented
    missing_categories = Column(JSON, default=list)
    present_categories = Column(JSON, default=list)
    expected_categories = Column(JSON, default=list)  # snapshot of what was evaluated this run
    incident_count = Column(Integer, default=0)
    incident_penalty_applied = Column(Integer, default=0)  # 0/1 — stored as int for simple SQL filtering

    computed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AssetKnowledgeGap asset_id={self.asset_id} gap_score={self.gap_score}>"
