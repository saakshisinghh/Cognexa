"""
apps/api/models/agent.py

Phase 5 models — Agentic AI Platform.

NOT explicitly named in the Phase 5 file list, but required to satisfy
spec requirements that ARE explicitly listed and cannot work without
persistence: "Execution History", "Execution Logs", "List Agents" with
enable/disable/versioning, and audit of every agent action. Kept in its
own module (matching the existing pattern of models/incident.py,
models/audit_log.py, models/conversation.py) and re-exported from
apps.api.models so Base.metadata.create_all() in main.py's lifespan
picks it up automatically alongside every other phase's tables — no
change to that startup code was needed.

Three tables:
    AgentDefinition   — registry row per agent (enabled/disabled, version)
    AgentExecution     — one row per agent run (goal, status, confidence, timing)
    AgentExecutionStep — one row per LangGraph node/tool step within a run
                         (mirrors AgentState.execution_history for durable
                         storage + the frontend ExecutionLogs/Timeline views)
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, DateTime, JSON,
    ForeignKey, Enum as SAEnum, Index, func,
)
from sqlalchemy.orm import relationship

from apps.api.db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class AgentExecutionMode(str, enum.Enum):
    single = "single"
    sequential = "sequential"
    parallel = "parallel"
    supervisor = "supervisor"


class AgentExecutionStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentDefinition(Base):
    """Registry row for a discoverable agent. Populated at startup by
    services/agent_registry.py from the in-code agent classes, then
    mutable at runtime (enable/disable) via the Agent API."""
    __tablename__ = "agent_definitions"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_key = Column(String(64), unique=True, nullable=False, index=True)  # e.g. "rca_agent"
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="1.0.0")
    capabilities = Column(JSON, default=list)   # tool names this agent may use
    is_enabled = Column(Boolean, default=True, nullable=False)
    health_status = Column(String(20), default="unknown")  # ok | degraded | error | unknown
    last_health_check_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentExecution(Base):
    """One row per agent run, single-agent or as part of a multi-agent workflow."""
    __tablename__ = "agent_executions"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_key = Column(String(64), nullable=False, index=True)
    workflow_id = Column(String, ForeignKey("agent_workflows.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    goal = Column(Text, nullable=False)
    context = Column(JSON, default=dict)
    mode = Column(SAEnum(AgentExecutionMode), default=AgentExecutionMode.single, nullable=False)
    status = Column(SAEnum(AgentExecutionStatus), default=AgentExecutionStatus.queued, nullable=False, index=True)

    plan = Column(JSON, nullable=True)
    answer = Column(Text, nullable=True)
    structured_output = Column(JSON, nullable=True)
    confidence = Column(JSON, nullable=True)
    sources = Column(JSON, default=list)
    errors = Column(JSON, default=list)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Float, nullable=True)

    celery_task_id = Column(String, nullable=True, index=True)
    cancel_requested = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_agent_executions_agent_created", "agent_key", "created_at"),
    )

    steps = relationship("AgentExecutionStep", back_populates="execution", cascade="all, delete-orphan",
                          order_by="AgentExecutionStep.sequence")


class AgentExecutionStep(Base):
    """Durable mirror of AgentState.execution_history entries — one row per
    LangGraph node/tool step, for the ExecutionLogs / ToolCallTimeline UI."""
    __tablename__ = "agent_execution_steps"

    id = Column(String, primary_key=True, default=generate_uuid)
    execution_id = Column(String, ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, default=0)
    step_name = Column(String(120), nullable=False)   # e.g. "planner", "tool:semantic_search"
    status = Column(String(20), nullable=False)        # started | completed | failed | retried
    detail = Column(Text, nullable=True)
    duration_ms = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    execution = relationship("AgentExecution", back_populates="steps")


class AgentWorkflow(Base):
    """A multi-agent collaboration run (sequential/parallel/supervisor),
    grouping one or more AgentExecution rows."""
    __tablename__ = "agent_workflows"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    goal = Column(Text, nullable=False)
    mode = Column(SAEnum(AgentExecutionMode), default=AgentExecutionMode.sequential, nullable=False)
    agent_keys = Column(JSON, default=list)   # ordered list of agent_key participants
    status = Column(SAEnum(AgentExecutionStatus), default=AgentExecutionStatus.queued, nullable=False, index=True)
    shared_context = Column(JSON, default=dict)
    final_answer = Column(Text, nullable=True)
    conflicts = Column(JSON, default=list)   # unresolved / resolved cross-agent conflicts
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
