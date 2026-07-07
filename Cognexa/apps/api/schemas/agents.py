"""
apps/api/schemas/agents.py

Phase 5 — Pydantic request/response models for the Agent API
(routers/agents.py). Additive — does not modify any Phase 1-4 schema.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Agent catalog ───────────────────────────────────────────────────────

class ToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict
    sensitive: bool = False


class AgentDescriptor(BaseModel):
    agent_key: str
    name: str
    description: str
    version: str
    capabilities: list[str]
    is_enabled: bool
    health_status: str = "unknown"


class AgentListResponse(BaseModel):
    agents: list[AgentDescriptor]


class AgentUpdateRequest(BaseModel):
    is_enabled: Optional[bool] = None


class AgentHealthResponse(BaseModel):
    agent_key: str
    status: str
    checked_at: datetime
    detail: Optional[str] = None


# ── Running an agent ─────────────────────────────────────────────────────

class RunAgentRequest(BaseModel):
    goal: str = Field(..., min_length=3, max_length=4000)
    context: dict = Field(default_factory=dict)
    stream: bool = False


class RunWorkflowRequest(BaseModel):
    goal: str = Field(..., min_length=3, max_length=4000)
    agent_keys: list[str] = Field(..., min_length=1, max_length=4)
    mode: str = Field(default="sequential")  # sequential | parallel | supervisor
    context: dict = Field(default_factory=dict)


# ── Execution results ────────────────────────────────────────────────────

class ExecutionStepOut(BaseModel):
    step: str
    status: str
    detail: str
    timestamp: str
    duration_ms: Optional[float] = None


class ExecutionSummary(BaseModel):
    execution_id: str
    agent_key: str
    goal: str
    status: str
    mode: str
    workflow_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    confidence: Optional[dict] = None


class ExecutionDetail(ExecutionSummary):
    plan: Optional[dict] = None
    answer: Optional[str] = None
    structured_output: Optional[dict] = None
    sources: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    steps: list[ExecutionStepOut] = Field(default_factory=list)


class ExecutionListResponse(BaseModel):
    executions: list[ExecutionSummary]
    total: int


class ExecutionLogsResponse(BaseModel):
    execution_id: str
    steps: list[ExecutionStepOut]


class CancelExecutionResponse(BaseModel):
    execution_id: str
    status: str


# ── Workflows ────────────────────────────────────────────────────────────

class WorkflowStepOut(BaseModel):
    agent_key: str
    execution_id: str
    status: str
    answer: Optional[str] = None
    confidence: Optional[dict] = None


class WorkflowDetail(BaseModel):
    workflow_id: str
    goal: str
    mode: str
    status: str
    agent_keys: list[str]
    steps: list[WorkflowStepOut]
    final_answer: Optional[str] = None
    conflicts: list[dict] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None


# ── Streaming events (SSE payload shapes — documented for the frontend) ──

class StreamNodeEvent(BaseModel):
    type: str = "node"
    node: str
    output: dict[str, Any]


class StreamDoneEvent(BaseModel):
    type: str = "done"
    execution_id: str
    status: str
