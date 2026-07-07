"""
apps/api/routers/agents.py

Phase 5 — Agent API.

Reuses the existing auth/RBAC dependencies (get_current_user, require_role)
from Phase 1's routers/auth.py — not reimplemented here, per project
convention (see routers/graph.py for the same pattern).

Endpoints
---------
GET    /api/v1/agents                          List agents (catalog)
GET    /api/v1/agents/{agent_key}               Agent detail
PATCH  /api/v1/agents/{agent_key}                Enable/disable (admin only)
GET    /api/v1/agents/{agent_key}/health         Health check
GET    /api/v1/agents/health                    Health check all

POST   /api/v1/agents/{agent_key}/run            Run agent (sync or streaming)
POST   /api/v1/agents/{agent_key}/cancel/{execution_id}  Cancel a running execution

GET    /api/v1/agents/executions                List execution history (filterable)
GET    /api/v1/agents/executions/{execution_id}  Execution detail
GET    /api/v1/agents/executions/{execution_id}/logs  Execution logs/timeline

POST   /api/v1/agents/workflows                  Run a multi-agent workflow
GET    /api/v1/agents/workflows/{workflow_id}    Workflow detail

IMPORTANT — route registration order:
Starlette/FastAPI matches routes in the order they're added. Any route
with a single path segment after /agents (e.g. "/executions", "/health",
"/workflows") MUST be registered BEFORE "/{agent_key}" for the same HTTP
method, or the {agent_key} path-param route will greedily match first and
the specific route becomes unreachable (this bit us once already — see
git history / chat log for the "GET /agents/executions always 404s"
incident). Routes with additional segments (e.g. "/executions/{id}",
"/workflows/{id}") are NOT affected, since their shape differs from
"/{agent_key}" and Starlette disambiguates by segment count.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.routers.auth import get_current_user, require_engineer_or_admin, require_admin
from apps.api.models import User
from apps.api.models.agent import AgentExecution, AgentExecutionStep, AgentWorkflow, AgentExecutionStatus
from apps.api.schemas.agents import (
    AgentListResponse, AgentDescriptor, AgentUpdateRequest, AgentHealthResponse,
    RunAgentRequest, RunWorkflowRequest,
    ExecutionSummary, ExecutionDetail, ExecutionListResponse, ExecutionStepOut,
    ExecutionLogsResponse, CancelExecutionResponse,
    WorkflowDetail, WorkflowStepOut,
)
from apps.api.services import agent_registry, agent_executor, workflow_engine
from apps.api.services.audit import write_audit_log

logger = logging.getLogger("indusmind.agents.router")

router = APIRouter()


# ════════════════════════════════════════════════════════════════════════
#  Agent catalog (top-level, no-path-param routes FIRST)
# ════════════════════════════════════════════════════════════════════════

@router.get("", response_model=AgentListResponse)
def list_agents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    definitions = agent_registry.list_agent_definitions(db)
    return AgentListResponse(agents=[
        AgentDescriptor(
            agent_key=d.agent_key, name=d.name, description=d.description or "", version=d.version,
            capabilities=d.capabilities or [], is_enabled=d.is_enabled, health_status=d.health_status,
        )
        for d in definitions
    ])


@router.get("/health")
def health_check_all(db: Session = Depends(get_db), current_user: User = Depends(require_engineer_or_admin)):
    return {"results": agent_registry.health_check_all(db)}


# ════════════════════════════════════════════════════════════════════════
#  Execution history / logs — registered BEFORE /{agent_key} (see note above)
# ════════════════════════════════════════════════════════════════════════

def _execution_to_summary(e: AgentExecution) -> ExecutionSummary:
    return ExecutionSummary(
        execution_id=e.id, agent_key=e.agent_key, goal=e.goal, status=e.status.value,
        mode=e.mode.value, workflow_id=e.workflow_id, created_at=e.created_at,
        started_at=e.started_at, completed_at=e.completed_at, duration_ms=e.duration_ms,
        confidence=e.confidence,
    )


@router.get("/executions", response_model=ExecutionListResponse)
def list_executions(
    agent_key: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    q = db.query(AgentExecution).filter(AgentExecution.user_id == current_user.id)
    if agent_key:
        q = q.filter(AgentExecution.agent_key == agent_key)
    if status_filter:
        try:
            q = q.filter(AgentExecution.status == AgentExecutionStatus(status_filter))
        except ValueError:
            raise HTTPException(400, f"Invalid status '{status_filter}'")
    total = q.count()
    rows = q.order_by(AgentExecution.created_at.desc()).offset(offset).limit(limit).all()
    return ExecutionListResponse(executions=[_execution_to_summary(r) for r in rows], total=total)


def _execution_detail(db: Session, execution_id: str) -> ExecutionDetail:
    execution = db.query(AgentExecution).filter(AgentExecution.id == execution_id).first()
    if execution is None:
        raise HTTPException(404, "Execution not found")
    steps = (
        db.query(AgentExecutionStep)
        .filter(AgentExecutionStep.execution_id == execution_id)
        .order_by(AgentExecutionStep.sequence.asc())
        .all()
    )
    return ExecutionDetail(
        **_execution_to_summary(execution).model_dump(),
        plan=execution.plan, answer=execution.answer, structured_output=execution.structured_output,
        sources=execution.sources or [], errors=execution.errors or [],
        steps=[
            ExecutionStepOut(
                step=s.step_name, status=s.status, detail=s.detail or "",
                timestamp=s.timestamp.isoformat() if s.timestamp else "", duration_ms=s.duration_ms,
            )
            for s in steps
        ],
    )


@router.get("/executions/{execution_id}", response_model=ExecutionDetail)
def get_execution(execution_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _execution_detail(db, execution_id)


@router.get("/executions/{execution_id}/logs", response_model=ExecutionLogsResponse)
def get_execution_logs(execution_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    execution = db.query(AgentExecution).filter(AgentExecution.id == execution_id).first()
    if execution is None:
        raise HTTPException(404, "Execution not found")
    steps = (
        db.query(AgentExecutionStep)
        .filter(AgentExecutionStep.execution_id == execution_id)
        .order_by(AgentExecutionStep.sequence.asc())
        .all()
    )
    return ExecutionLogsResponse(execution_id=execution_id, steps=[
        ExecutionStepOut(step=s.step_name, status=s.status, detail=s.detail or "",
                          timestamp=s.timestamp.isoformat() if s.timestamp else "", duration_ms=s.duration_ms)
        for s in steps
    ])


# ════════════════════════════════════════════════════════════════════════
#  Workflows (multi-agent) — registered BEFORE /{agent_key} (see note above)
# ════════════════════════════════════════════════════════════════════════

def _workflow_detail(db: Session, workflow_id: str) -> WorkflowDetail:
    workflow = db.query(AgentWorkflow).filter(AgentWorkflow.id == workflow_id).first()
    if workflow is None:
        raise HTTPException(404, "Workflow not found")
    executions = workflow_engine.get_workflow_executions(db, workflow_id)
    return WorkflowDetail(
        workflow_id=workflow.id, goal=workflow.goal, mode=workflow.mode.value, status=workflow.status.value,
        agent_keys=workflow.agent_keys or [], final_answer=workflow.final_answer,
        conflicts=workflow.conflicts or [], created_at=workflow.created_at, completed_at=workflow.completed_at,
        steps=[
            WorkflowStepOut(agent_key=e.agent_key, execution_id=e.id, status=e.status.value,
                             answer=e.answer, confidence=e.confidence)
            for e in executions
        ],
    )


@router.post("/workflows", response_model=WorkflowDetail)
async def run_workflow(
    payload: RunWorkflowRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    if payload.mode not in ("sequential", "parallel", "supervisor"):
        raise HTTPException(400, "mode must be one of: sequential, parallel, supervisor")
    try:
        workflow = await workflow_engine.run_workflow(
            db, goal=payload.goal, agent_keys=payload.agent_keys, mode=payload.mode,
            context=payload.context, current_user=current_user,
        )
    except agent_executor.AgentNotFoundError as exc:
        raise HTTPException(400, str(exc))
    return _workflow_detail(db, workflow.id)


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(workflow_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _workflow_detail(db, workflow_id)


# ════════════════════════════════════════════════════════════════════════
#  Agent detail / management (path-param routes LAST, so they don't
#  swallow the specific routes above)
# ════════════════════════════════════════════════════════════════════════

@router.get("/{agent_key}", response_model=AgentDescriptor)
def get_agent_detail(agent_key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    d = agent_registry.get_agent_definition(db, agent_key)
    if d is None:
        raise HTTPException(404, "Agent not found")
    return AgentDescriptor(
        agent_key=d.agent_key, name=d.name, description=d.description or "", version=d.version,
        capabilities=d.capabilities or [], is_enabled=d.is_enabled, health_status=d.health_status,
    )


@router.patch("/{agent_key}", response_model=AgentDescriptor)
def update_agent(
    agent_key: str, payload: AgentUpdateRequest,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    if payload.is_enabled is None:
        raise HTTPException(400, "Nothing to update")
    row = agent_registry.set_enabled(db, agent_key, payload.is_enabled)
    if row is None:
        raise HTTPException(404, "Agent not found")
    write_audit_log(
        db, action="agent_enable" if payload.is_enabled else "agent_disable",
        status="success", user_id=current_user.id, resource=f"agent:{agent_key}",
    )
    return AgentDescriptor(
        agent_key=row.agent_key, name=row.name, description=row.description or "", version=row.version,
        capabilities=row.capabilities or [], is_enabled=row.is_enabled, health_status=row.health_status,
    )


@router.get("/{agent_key}/health", response_model=AgentHealthResponse)
def health_check_one(agent_key: str, db: Session = Depends(get_db), current_user: User = Depends(require_engineer_or_admin)):
    result = agent_registry.health_check(db, agent_key)
    return AgentHealthResponse(**result)


@router.post("/{agent_key}/run")
async def run_agent(
    agent_key: str, payload: RunAgentRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    if payload.stream:
        async def event_stream():
            try:
                async for event in agent_executor.stream_agent(
                    db, agent_key=agent_key, goal=payload.goal,
                    context=payload.context, current_user=current_user,
                ):
                    yield f"data: {json.dumps(event, default=str)}\n\n"
            except agent_executor.AgentNotFoundError as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            except agent_executor.AgentRateLimitError as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

        return StreamingResponse(
            event_stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        execution = await agent_executor.execute_agent(
            db, agent_key=agent_key, goal=payload.goal, context=payload.context, current_user=current_user,
        )
    except agent_executor.AgentNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except agent_executor.AgentRateLimitError as exc:
        raise HTTPException(429, str(exc))

    return _execution_detail(db, execution.id)


@router.post("/{agent_key}/cancel/{execution_id}", response_model=CancelExecutionResponse)
def cancel_execution(
    agent_key: str, execution_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    execution = agent_executor.request_cancellation(db, execution_id)
    if execution is None:
        raise HTTPException(404, "Execution not found")
    write_audit_log(
        db, action="agent_cancel", status="success", user_id=current_user.id,
        resource=f"agent_execution:{execution_id}",
    )
    return CancelExecutionResponse(execution_id=execution_id, status="cancel_requested")