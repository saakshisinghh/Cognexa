"""
apps/api/models/knowledge_loss.py

Phase 6 — Knowledge Loss Prediction.

Two brand-new tables (auto-created by Base.metadata.create_all() at next
API boot — they don't exist yet, so no manual ALTER needed for these two;
see phase6_loss.sql for the one manual ALTER this feature does need, on
the existing `users` table):

    AssetExpertiseOwnership  — one row per (asset_id, user_id): how much
                               of an asset's document/incident history a
                               given user is responsible for.
    AssetKnowledgeLossRisk   — one row per asset: the aggregated risk
                               score, primary owner, and mitigation text.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, Text, DateTime, ForeignKey,
    UniqueConstraint, CheckConstraint, func,
)

from apps.api.db import Base


def generate_uuid():
    return str(uuid.uuid4())


class AssetExpertiseOwnership(Base):
    __tablename__ = "asset_expertise_ownership"
    __table_args__ = (UniqueConstraint("asset_id", "user_id", name="uq_asset_expertise_owner"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    document_count = Column(Integer, default=0)
    incident_count = Column(Integer, default=0)
    ownership_score = Column(Float, nullable=False, default=0.0)  # this user's share, 0..1
    is_primary_owner = Column(Boolean, default=False)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)

    computed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AssetExpertiseOwnership asset_id={self.asset_id} user_id={self.user_id} score={self.ownership_score}>"


class AssetKnowledgeLossRisk(Base):
    __tablename__ = "asset_knowledge_loss_risk"
    __table_args__ = (
        CheckConstraint("risk_score >= 0.0 AND risk_score <= 1.0", name="ck_asset_loss_risk_score_range"),
        CheckConstraint("concentration_score >= 0.0 AND concentration_score <= 1.0", name="ck_asset_loss_concentration_range"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    primary_owner_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    concentration_score = Column(Float, nullable=False, default=0.0)  # primary owner's ownership_score
    contributor_count = Column(Integer, default=0)  # distinct users with any activity — "bus factor"
    retirement_boost_applied = Column(Boolean, default=False)

    risk_score = Column(Float, nullable=False, default=0.0)  # 0..1
    risk_level = Column(String, nullable=False, default="unknown")  # unknown|low|medium|high|critical
    mitigation_recommendation = Column(Text, nullable=True)

    computed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AssetKnowledgeLossRisk asset_id={self.asset_id} risk_score={self.risk_score} level={self.risk_level}>"
