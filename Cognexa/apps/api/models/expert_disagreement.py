"""
apps/api/models/expert_disagreement.py

Phase 6 — Expert Disagreement Detection.

One row per unique (asset_id, document_a_id, document_b_id, topic)
cluster — recurring contradictions across MANY historical queries
(query_history.conflicts_json, populated by Phase 4's
services/retrieval/conflict_detector.py on every copilot answer),
aggregated nightly by workers/disagreement_tasks.py.

A single conflict flagged once in one query is noise; the same two
documents contradicting each other on the same topic across repeated,
independent queries is a real, persistent disagreement worth surfacing
and resolving — that distinction is the entire point of this table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Column, String, Integer, Boolean, Text, DateTime, ForeignKey,
    UniqueConstraint, func,
)

from apps.api.db import Base


def generate_uuid():
    return str(uuid.uuid4())


class AssetExpertDisagreement(Base):
    __tablename__ = "asset_expert_disagreements"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "document_a_id", "document_b_id", "topic",
            name="uq_asset_disagreement_cluster",
        ),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    topic = Column(String, nullable=False)  # e.g. "lubrication_interval" — see conflict_detector.py

    # Canonically ordered (document_a_id < document_b_id as strings) so
    # the same pair is never stored twice in reversed order.
    document_a_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    document_a_title = Column(String, nullable=False)
    document_b_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    document_b_title = Column(String, nullable=False)

    occurrence_count = Column(Integer, nullable=False, default=1)
    max_severity = Column(String, nullable=False, default="minor")  # minor|moderate|major
    sample_excerpt_a = Column(Text, nullable=True)
    sample_excerpt_b = Column(Text, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    # Manual resolution workflow — an engineer determines which document
    # is authoritative (or that both need updating) and marks it resolved.
    # Auto-reopened by the nightly task if a NEW occurrence appears after
    # resolved_at (see workers/disagreement_tasks.py) — a fresh occurrence
    # after "resolution" means the underlying docs still disagree.
    is_resolved = Column(Boolean, nullable=False, default=False)
    resolved_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    computed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return (
            f"<AssetExpertDisagreement asset_id={self.asset_id} topic={self.topic} "
            f"occurrences={self.occurrence_count} resolved={self.is_resolved}>"
        )
