"""
apps/api/services/agent_executor.py

Phase 5 — Agent Executor.

Owns the full lifecycle of a SINGLE agent execution:
    - permission check (RBAC — only enabled agents, role-gated sensitive tools)
    - rate limiting (per-user, Redis fixed-window)
    - persisting the AgentExecution row + AgentExecutionStep rows (durable
      Execution History / Execution Logs, reusing the Phase 2 Postgres
      audit trail conventions)
    - auditing every execution via the existing services.audit.write_audit_log
    - running the agent's LangGraph (sync `run()` or streaming `stream()`)
    - cancellation (cooperative — checked at the top of retriever/tool_executor
      passes so a running execution stops promptly without killing the process)

Multi-agent orchestration (sequential/parallel/supervisor) is layered ON
TOP of this module by services/workflow_engine.py, which calls
`execute_agent()` once per participating agent rather than duplicating
any of this lifecycle logic.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from sqlalchemy.orm import Session

from apps.api.models.agent import (
    AgentExecution, AgentExecutionStep, AgentExecutionStatus, AgentExecutionMode,
)
from apps.api.models import User
from apps.api.services import agent_registry
from apps.api.services.audit import write_audit_log
from apps.api.redis_client import get_redis

logger = logging.getLogger("indusmind.agents.executor")

_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_EXECUTIONS = 10  # per user per window — generous for interactive use, blocks runaway loops


class AgentPermissionError(Exception):
    pass


class AgentRateLimitError(Exception):
    pass


class AgentNotFoundError(Exception):
    pass


def _check_rate_limit(user_id: Optional[str]) -> None:
    if not user_id:
        return
    key = f"agent:ratelimit:{user_id}"
    try:
        r = get_redis()
        count = r.incr(key)
        if count == 1:
            r.expire(key, _RATE_LIMIT_WINDOW_SECONDS)
        if count > _RATE_LIMIT_MAX_EXECUTIONS:
            raise AgentRateLimitError(
                f"Rate limit exceeded: max {_RATE_LIMIT_MAX_EXECUTIONS} agent executions per "
                f"{_RATE_LIMIT_WINDOW_SECONDS}s"
            )
    except AgentRateLimitError:
        raise
    except Exception as exc:  # noqa: BLE001 — Redis outage must not block execution
        logger.warning("agent_rate_limit_check_failed error=%s (allowing request)", exc)


def _persist_steps(db: Session, execution_id: str, execution_history: list[dict]) -> None:
    for idx, step in enumerate(execution_history):
        db.add(AgentExecutionStep(
            execution_id=execution_id,
            sequence=idx,
            step_name=step.get("step", "unknown"),
            status=step.get("status", "completed"),
            detail=step.get("detail", ""),
            duration_ms=step.get("duration_ms"),
        ))
    db.commit()


def create_execution_row(
    db: Session, *, agent_key: str, goal: str, context: dict,
    user_id: Optional[str], workflow_id: Optional[str] = None,
    mode: AgentExecutionMode = AgentExecutionMode.single,
) -> AgentExecution:
    execution = AgentExecution(
        agent_key=agent_key, goal=goal, context=context, user_id=user_id,
        workflow_id=workflow_id, mode=mode, status=AgentExecutionStatus.queued,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def request_cancellation(db: Session, execution_id: str) -> Optional[AgentExecution]:
    execution = db.query(AgentExecution).filter(AgentExecution.id == execution_id).first()
    if execution is None:
        return None
    execution.cancel_requested = True
    db.commit()
    db.refresh(execution)
    return execution


def _is_cancelled(db: Session, execution_id: str) -> bool:
    execution = db.query(AgentExecution).filter(AgentExecution.id == execution_id).first()
    return bool(execution and execution.cancel_requested)


async def execute_agent(
    db: Session, *, agent_key: str, goal: str, context: Optional[dict] = None,
    current_user: Optional[User] = None, workflow_id: Optional[str] = None,
    execution: Optional[AgentExecution] = None,
) -> AgentExecution:
    """
    Runs one agent to completion (non-streaming) and persists the full
    result. Returns the updated AgentExecution row.
    """
    context = context or {}
    user_id = getattr(current_user, "id", None)

    agent = agent_registry.get_agent(db, agent_key)
    if agent is None:
        raise AgentNotFoundError(f"Agent '{agent_key}' is not registered or is disabled")

    _check_rate_limit(user_id)

    if execution is None:
        execution = create_execution_row(
            db, agent_key=agent_key, goal=goal, context=context,
            user_id=user_id, workflow_id=workflow_id,
        )

    execution.status = AgentExecutionStatus.running
    execution.started_at = datetime.now(timezone.utc)
    db.commit()

    write_audit_log(
        db, action="agent_execute", status="success", user_id=user_id,
        resource=f"agent:{agent_key}", detail=f"execution_id={execution.id} goal={goal[:200]!r}",
    )

    start = time.monotonic()
    try:
        final_state = await agent.run(execution.id, goal, db, user_id=user_id, context=context)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        db.refresh(execution)
        if execution.cancel_requested:
            execution.status = AgentExecutionStatus.cancelled
        else:
            execution.status = AgentExecutionStatus.completed
        execution.plan = final_state.get("plan")
        execution.answer = final_state.get("answer")
        execution.structured_output = final_state.get("structured_output")
        execution.confidence = final_state.get("confidence")
        execution.sources = final_state.get("sources", [])
        execution.errors = final_state.get("errors", [])
        execution.duration_ms = duration_ms
        execution.completed_at = datetime.now(timezone.utc)
        db.commit()

        _persist_steps(db, execution.id, final_state.get("execution_history", []))
        return execution

    except Exception as exc:  # noqa: BLE001
        logger.exception("agent_execution_failed agent_key=%s execution_id=%s", agent_key, execution.id)
        db.refresh(execution)
        execution.status = AgentExecutionStatus.failed
        execution.errors = (execution.errors or []) + [{
            "node": "executor", "message": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(), "recoverable": False,
        }]
        execution.completed_at = datetime.now(timezone.utc)
        db.commit()
        write_audit_log(
            db, action="agent_execute", status="failure", user_id=user_id,
            resource=f"agent:{agent_key}", detail=f"execution_id={execution.id} error={exc}",
        )
        return execution


async def stream_agent(
    db: Session, *, agent_key: str, goal: str, context: Optional[dict] = None,
    current_user: Optional[User] = None,
) -> AsyncGenerator[dict, None]:
    """
    Streaming counterpart to execute_agent(): yields one dict per
    completed LangGraph node, then a final `{"type": "done", ...}` event.
    Persists identically to execute_agent() once the stream completes.
    """
    context = context or {}
    user_id = getattr(current_user, "id", None)

    agent = agent_registry.get_agent(db, agent_key)
    if agent is None:
        raise AgentNotFoundError(f"Agent '{agent_key}' is not registered or is disabled")

    _check_rate_limit(user_id)

    execution = create_execution_row(db, agent_key=agent_key, goal=goal, context=context, user_id=user_id)
    execution.status = AgentExecutionStatus.running
    execution.started_at = datetime.now(timezone.utc)
    db.commit()

    write_audit_log(
        db, action="agent_execute", status="success", user_id=user_id,
        resource=f"agent:{agent_key}", detail=f"execution_id={execution.id} (streaming) goal={goal[:200]!r}",
    )

    start = time.monotonic()
    last_state: dict = {}
    step_sequence = 0
    try:
        async for event in agent.stream(execution.id, goal, db, user_id=user_id, context=context):
            node_name = event["node"]
            output = event["output"]
            last_state.update(output)

            for step in output.get("execution_history", []):
                db.add(AgentExecutionStep(
                    execution_id=execution.id, sequence=step_sequence,
                    step_name=step.get("step", node_name), status=step.get("status", "completed"),
                    detail=step.get("detail", ""), duration_ms=step.get("duration_ms"),
                ))
                step_sequence += 1
            db.commit()

            if _is_cancelled(db, execution.id):
                execution.status = AgentExecutionStatus.cancelled
                execution.completed_at = datetime.now(timezone.utc)
                db.commit()
                yield {"type": "done", "execution_id": execution.id, "status": "cancelled"}
                return

            yield {"type": "node", "node": node_name, "output": output}

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        db.refresh(execution)
        execution.status = AgentExecutionStatus.completed
        execution.answer = last_state.get("answer")
        execution.plan = last_state.get("plan")
        execution.structured_output = last_state.get("structured_output")
        execution.confidence = last_state.get("confidence")
        execution.sources = last_state.get("sources", [])
        execution.duration_ms = duration_ms
        execution.completed_at = datetime.now(timezone.utc)
        db.commit()

        yield {"type": "done", "execution_id": execution.id, "status": "completed"}

    except Exception as exc:  # noqa: BLE001
        logger.exception("agent_stream_failed agent_key=%s execution_id=%s", agent_key, execution.id)
        db.refresh(execution)
        execution.status = AgentExecutionStatus.failed
        execution.completed_at = datetime.now(timezone.utc)
        db.commit()
        yield {"type": "error", "execution_id": execution.id, "message": str(exc)}
