from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Enum, JSON, BigInteger, func
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from apps.api.db import Base


def generate_uuid():
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    admin = "admin"
    engineer = "engineer"
    viewer = "viewer"


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.engineer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    # ─── Phase 6: Knowledge Loss Prediction — manual HR signal ───────────
    # There is no hire_date/tenure/HR data anywhere in this schema, so
    # "retirement risk" cannot be organically derived. This flag is set
    # manually by an admin (PATCH /api/v1/loss/users/{user_id}/retirement-flag)
    # based on real HR knowledge the system has no other way to know.
    # Combined with the (organically computed) knowledge-concentration
    # score in AssetKnowledgeLossRisk — see services/loss.py.
    is_retirement_risk = Column(Boolean, nullable=False, default=False)
    retirement_risk_notes = Column(Text, nullable=True)

    documents = relationship("Document", back_populates="owner")
    assets = relationship("Asset", back_populates="owner")
    conversations = relationship("Conversation", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=generate_uuid)
    token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="refresh_tokens")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    asset_type = Column(String, nullable=True)
    owner_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tags = Column(JSON, default=list)
    extra_metadata = Column("metadata", JSON, default=dict)
    health_status = Column(String, default="unknown")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="assets")
    documents = relationship("Document", back_populates="asset")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=generate_uuid)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)
    mime_type = Column(String, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.pending, nullable=False)
    ocr_status = Column(String, default="pending")
    embedding_status = Column(String, default="pending")
    chunk_count = Column(Integer, default=0)
    entity_count = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    language = Column(String, nullable=True)
    category = Column(String, nullable=True)
    tags = Column(JSON, default=list)
    extra_metadata = Column("metadata", JSON, default=dict)
    extracted_text = Column(Text, nullable=True)
    owner_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ─── Phase 6: Temporal Knowledge Intelligence — stale-document flag ──
    # Set by workers/temporal_tasks.py::flag_stale_documents_task, based on
    # the average trust_score across this document's chunks dropping below
    # a threshold. Read-only from the API's perspective except for the
    # nightly job and the manual override endpoint.
    is_stale = Column(Boolean, nullable=False, default=False)
    stale_flagged_at = Column(DateTime(timezone=True), nullable=True)
    stale_reason = Column(Text, nullable=True)

    owner = relationship("User", back_populates="documents")
    asset = relationship("Asset", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="document")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    token_count = Column(Integer, default=0)
    weaviate_id = Column(String, nullable=True)
    extra_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ─── Phase 6: Temporal Knowledge Intelligence ────────────────────────
    # Additive only — existing columns/behavior above are untouched.
    # valid_from defaults to chunk creation time (when this information
    # entered the system); nullable=True only so existing rows created
    # before this migration don't need a backfill to pass NOT NULL.
    valid_from = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    # NULL = still currently valid. Set when a chunk is superseded.
    valid_to = Column(DateTime(timezone=True), nullable=True)
    # Self-referential FK to the chunk that replaces this one (if any).
    # ondelete=SET NULL: deleting the newer chunk shouldn't cascade-delete
    # the older, already-superseded chunk it replaced.
    superseded_by_chunk_id = Column(String, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True)
    # Decayed relevance score in [0.0, 1.0], recomputed nightly by
    # workers/temporal_tasks.py. Mirrors (and is the source of truth for)
    # the `trust_score` property already present on the Weaviate
    # DocumentChunk schema (see weaviate_client.py) — kept in sync by the
    # same nightly job so retrieval-time filtering reflects the same value.
    trust_score = Column(Float, nullable=False, default=1.0)
    decay_computed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="chunks")
    superseded_by = relationship(
        "Chunk",
        remote_side=[id],
        foreign_keys=[superseded_by_chunk_id],
        backref="supersedes",
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="conversations")
    document = relationship("Document", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    sources = Column(JSON, default=list)
    confidence = Column(Float, nullable=True)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
# ─── Phase 2: Audit Logging & Async Processing ───────────────────────────────
from apps.api.models.audit_log import (
    AuditLog, AuditAction, AuditStatus,
    ProcessingJob, JobStatus, JobStep,
    TaskExecution, TaskState,
    TaskMetrics, WorkerStatus, QueueStatistics,
)
# ─── Phase 6: Knowledge Gap Detection ─────────────────────────────────────
from apps.api.models.knowledge_gap import AssetKnowledgeGap
# ─── Phase 6: Knowledge Loss Prediction ───────────────────────────────────
from apps.api.models.knowledge_loss import AssetExpertiseOwnership, AssetKnowledgeLossRisk
# ─── Phase 6: Expert Disagreement Detection ───────────────────────────────
from apps.api.models.expert_disagreement import AssetExpertDisagreement
# ─── Phase 6: AI Shadow Engineer ──────────────────────────────────────────
from apps.api.models.expert_knowledge import ExpertKnowledgeEntry