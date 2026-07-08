"""
apps/api/models/expert_knowledge.py

Phase 6 — AI Shadow Engineer: expert knowledge capture.

Each row is one piece of tacit/tribal knowledge an expert has explicitly
recorded (a tip, a workaround, an explanation of "why we do it this way"
that never made it into a formal document). Embedded and indexed into a
SEPARATE Weaviate collection ("ExpertKnowledge" — see
weaviate_client.py::ensure_expert_knowledge_schema) rather than mixed
into the DocumentChunk collection, so persona-authored tacit knowledge
is never confused with or ranked identically to formal document content
unless a query explicitly asks for persona-aware retrieval.

This is the direct mitigation mechanism for Phase 6 Feature 3's
(Knowledge Loss Prediction) "mitigation_recommendation" — capturing an
at-risk expert's knowledge here is the concrete action that recommendation
is pointing at.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON, ForeignKey, func

from apps.api.db import Base


def generate_uuid():
    return str(uuid.uuid4())


class ExpertKnowledgeEntry(Base):
    __tablename__ = "expert_knowledge_entries"

    id = Column(String, primary_key=True, default=generate_uuid)
    author_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=True, index=True)  # nullable: general expertise, not asset-specific

    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(JSON, default=list)

    weaviate_id = Column(String, nullable=True)  # set once embedded/indexed
    is_active = Column(Boolean, nullable=False, default=True)  # soft-delete flag

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ExpertKnowledgeEntry id={self.id} author={self.author_user_id} title={self.title!r}>"
