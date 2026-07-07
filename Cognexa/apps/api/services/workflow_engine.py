"""
apps/api/services/workflow_engine.py

Phase 5 — Workflow Engine: multi-agent collaboration on top of
services/agent_executor.py's single-agent execution primitive.

Supports the four patterns required by the spec:

    single      — one agent, one execution (handled directly by agent_executor;
                  included here only for a uniform `run_workflow` entrypoint)
    sequential  — agents run one after another; each agent receives the prior
                  agents' answers as HANDOFF CONTEXT (shared_context), so e.g.
                  the RCA Agent's findings feed into the Maintenance Agent's plan
    parallel    — agents run concurrently against the same goal/context,
                  independent of each other, then results are aggregated
    supervisor  — an LLM supervisor reads the goal and available agents, decides
                  which agent(s) to invoke and in what order (bounded to the
                  agent_keys the caller authorized), then runs them sequentially

Shared context / shared memory: all participating agents in a workflow read
from and contribute to the SAME `AgentWorkflow.shared_context` dict, which is
handed to each agent as part of its execution `context` — this is the
mechanism for cross-agent context sharing (distinct from each agent's own
short-term ExecutionMemory in agents/memory.py, which remains execution-scoped).

Conflict resolution: after all participating agents complete, a lightweight
LLM-based reconciliation step compares their answers/confidence levels and
flags disagreements rather than silently picking one — flagged conflicts are
stored on the workflow row for the frontend WorkflowGraph to surface.

── Fix (see routers/agents.py) ───────────────────────────────────────────
Multi-agent runs can take far longer than a single HTTP request should
block for (each participating agent may itself make several LLM calls,
plus the conflict-detection and final-answer-synthesis calls this module
makes AFTER all agents finish). The router no longer awaits the full run
inline; it now only creates+validates the workflow row synchronously
(`validate_and_create_workflow`, fast) and hands the actual execution
(`execute_workflow_background`) to FastAPI's BackgroundTasks, which runs
after the response is sent. Because that execution now happens outside
the request's lifetime, it CANNOT reuse the request-scoped `db` session
(which is closed as soon as the request completes) — it opens its own
session via `SessionLocal()` and closes it when done. The frontend's
workflow detail page already polls `GET /workflows/{id}` while status is
queued/running, so this is a drop-in fix with no other frontend changes
beyond widening that poll condition (see app/agents/workflows/[id]/page.tsx).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from apps.api.db import SessionLocal
from apps.api.models.agent import AgentWorkflow, AgentExecution, AgentExecutionMode, AgentExecutionStatus
from apps.api.models import User
from apps.api.services import agent_registry, agent_executor
from apps.api.services.audit import write_audit_log
from apps.api.services.llm_gateway import complete_response, LLMUnavailableError

logger = logging.getLogger("indusmind.agents.workflow")


def _validate_agent_keys(db: Session, agent_keys: list[str]) -> list[str]:
    valid = []
    for key in agent_keys:
        if agent_registry.get_agent(db, key) is not None:
            valid.append(key)
        else:
            logger.warning("workflow_dropped_unknown_or_disabled_agent agent_key=%s", key)
    return valid


def create_workflow_row(
    db: Session, *, goal: str, agent_keys: list[str], mode: str, user_id: Optional[str],
) -> AgentWorkflow:
    workflow = AgentWorkflow(
        goal=goal, agent_keys=agent_keys, mode=AgentExecutionMode(mode),
        user_id=user_id, status=AgentExecutionStatus.queued, shared_context={},
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


def validate_and_create_workflow(
    db: Session, *, goal: str, agent_keys: list[str], mode: str,
    context: Optional[dict] = None, current_user: Optional[User] = None,
) -> AgentWorkflow:
    """
    Fast, synchronous part of running a workflow: validate the requested
    agents and persist a `queued` AgentWorkflow row. Safe to call inline
    from the request handler — does not touch any agent or LLM.
    """
    valid_keys = _validate_agent_keys(db, agent_keys)
    if not valid_keys:
        raise agent_executor.AgentNotFoundError("No valid/enabled agents in agent_keys")

    workflow = create_workflow_row(
        db, goal=goal, agent_keys=valid_keys, mode=mode, user_id=getattr(current_user, "id", None),
    )
    workflow.shared_context = dict(context or {})
    db.commit()
    db.refresh(workflow)
    return workflow


async def _run_sequential(db: Session, workflow: AgentWorkflow, current_user: Optional[User]) -> list[AgentExecution]:
    executions: list[AgentExecution] = []
    handoff_notes: list[str] = []

    for agent_key in workflow.agent_keys:
        context = dict(workflow.shared_context or {})
        if handoff_notes:
            context["prior_agent_findings"] = handoff_notes

        execution = await agent_executor.execute_agent(
            db, agent_key=agent_key, goal=workflow.goal, context=context,
            current_user=current_user, workflow_id=workflow.id,
        )
        executions.append(execution)
        if execution.answer:
            handoff_notes.append(f"[{agent_key}]: {execution.answer[:800]}")

        workflow.shared_context = {**(workflow.shared_context or {}), f"{agent_key}_confidence": execution.confidence}
        db.commit()

    return executions


async def _run_parallel(db: Session, workflow: AgentWorkflow, current_user: Optional[User]) -> list[AgentExecution]:
    context = dict(workflow.shared_context or {})
    tasks = [
        agent_executor.execute_agent(
            db, agent_key=agent_key, goal=workflow.goal, context=context,
            current_user=current_user, workflow_id=workflow.id,
        )
        for agent_key in workflow.agent_keys
    ]
    return list(await asyncio.gather(*tasks))


async def _plan_supervisor_order(goal: str, agent_keys: list[str], db: Session) -> list[str]:
    descriptors = [
        {"agent_key": k, "name": (a := agent_registry.get_agent_unchecked(k)) and a.name,
         "description": a.description if (a := agent_registry.get_agent_unchecked(k)) else ""}
        for k in agent_keys
    ]
    prompt = (
        "You are a supervisor coordinating specialist industrial AI agents. "
        f"Given the goal and available agents, choose which agents to invoke and in what order.\n"
        f"GOAL: {goal}\nAGENTS: {json.dumps(descriptors)}\n"
        'Respond with ONLY JSON: {"order": ["agent_key", ...]} using only agent_keys from the list above. '
        "Include only agents genuinely relevant to the goal (at least one)."
    )
    try:
        raw, _in, _out = await complete_response([
            {"role": "system", "content": "You are a precise JSON-only planning assistant."},
            {"role": "user", "content": prompt},
        ])
        cleaned = raw.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        parsed = json.loads(cleaned)
        order = [k for k in parsed.get("order", []) if k in agent_keys]
        return order or agent_keys
    except (LLMUnavailableError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("supervisor_planning_failed error=%s — falling back to given order", exc)
        return agent_keys


async def _run_supervisor(db: Session, workflow: AgentWorkflow, current_user: Optional[User]) -> list[AgentExecution]:
    ordered_keys = await _plan_supervisor_order(workflow.goal, workflow.agent_keys, db)
    workflow.agent_keys = ordered_keys
    db.commit()
    # Supervisor pattern executes its chosen order sequentially, with handoff,
    # identical to _run_sequential — the distinguishing behavior is *how the
    # order/participants were chosen* (by an LLM supervisor, not the caller).
    return await _run_sequential(db, workflow, current_user)


async def _detect_conflicts(executions: list[AgentExecution]) -> list[dict]:
    """Flags disagreement between participating agents rather than silently
    merging — e.g. contradictory confidence levels or answers on the same goal."""
    if len(executions) < 2:
        return []

    summaries = [
        {"agent_key": e.agent_key, "confidence": (e.confidence or {}).get("level"),
         "answer_excerpt": (e.answer or "")[:400]}
        for e in executions if e.status == AgentExecutionStatus.completed
    ]
    if len(summaries) < 2:
        return []

    prompt = (
        "Compare these agent outputs for the same goal. Identify any factual "
        "contradictions between them (not just differences in emphasis). "
        f"OUTPUTS: {json.dumps(summaries)}\n"
        'Respond with ONLY JSON: {"conflicts": [{"agents": ["a","b"], "issue": "..."}]}. '
        'If there are no contradictions, respond {"conflicts": []}.'
    )
    try:
        raw, _in, _out = await complete_response([
            {"role": "system", "content": "You are a precise, conservative conflict-detection assistant."},
            {"role": "user", "content": prompt},
        ])
        cleaned = raw.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        parsed = json.loads(cleaned)
        return parsed.get("conflicts", [])
    except (LLMUnavailableError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("conflict_detection_failed error=%s", exc)
        return []


async def _synthesize_final_answer(workflow: AgentWorkflow, executions: list[AgentExecution]) -> str:
    completed = [e for e in executions if e.status == AgentExecutionStatus.completed and e.answer]
    if not completed:
        return "No participating agent produced a completed answer."
    if len(completed) == 1:
        return completed[0].answer

    combined = "\n\n".join(f"[{e.agent_key}]\n{e.answer}" for e in completed)
    try:
        answer, _in, _out = await complete_response([
            {"role": "system", "content": (
                "You synthesize multiple specialist agent outputs into one coherent answer "
                "for the original goal. Preserve agent attributions where relevant."
            )},
            {"role": "user", "content": f"GOAL: {workflow.goal}\n\nAGENT OUTPUTS:\n{combined}"},
        ])
        return answer.strip()
    except LLMUnavailableError:
        return combined


async def _run_workflow_body(db: Session, workflow: AgentWorkflow, current_user: Optional[User]) -> None:
    """Shared execution body, given a workflow row that already exists and
    is already `running`. Runs the chosen mode, detects conflicts, synthesizes
    the final answer, and commits the terminal status. Raises on failure so
    the caller can record it (both callers below catch and persist `failed`)."""
    if workflow.mode == AgentExecutionMode.parallel:
        executions = await _run_parallel(db, workflow, current_user)
    elif workflow.mode == AgentExecutionMode.supervisor:
        executions = await _run_supervisor(db, workflow, current_user)
    else:
        executions = await _run_sequential(db, workflow, current_user)

    conflicts = await _detect_conflicts(executions)
    final_answer = await _synthesize_final_answer(workflow, executions)

    db.refresh(workflow)
    workflow.final_answer = final_answer
    workflow.conflicts = conflicts
    workflow.status = AgentExecutionStatus.completed
    workflow.completed_at = datetime.now(timezone.utc)
    db.commit()


async def execute_workflow_background(workflow_id: str, user_id: Optional[str]) -> None:
    """
    The actual multi-agent run. Called via FastAPI BackgroundTasks AFTER the
    response for POST /agents/workflows has already been sent, so it must
    open its own DB session (the request-scoped one from Depends(get_db) is
    closed by then) and must not raise back into the caller.
    """
    db = SessionLocal()
    try:
        workflow = db.query(AgentWorkflow).filter(AgentWorkflow.id == workflow_id).first()
        if workflow is None:
            logger.error("execute_workflow_background: workflow_id=%s not found", workflow_id)
            return

        current_user = db.query(User).filter(User.id == user_id).first() if user_id else None

        workflow.status = AgentExecutionStatus.running
        workflow.started_at = datetime.now(timezone.utc)
        db.commit()

        write_audit_log(
            db, action="workflow_execute", status="success", user_id=user_id,
            resource=f"workflow:{workflow.id}", detail=f"mode={workflow.mode.value} agents={workflow.agent_keys}",
        )

        try:
            await _run_workflow_body(db, workflow, current_user)
        except Exception as exc:  # noqa: BLE001
            logger.exception("workflow_execution_failed workflow_id=%s", workflow.id)
            db.refresh(workflow)
            workflow.status = AgentExecutionStatus.failed
            workflow.completed_at = datetime.now(timezone.utc)
            db.commit()
            write_audit_log(
                db, action="workflow_execute", status="failure", user_id=user_id,
                resource=f"workflow:{workflow.id}", detail=str(exc),
            )
    finally:
        db.close()


async def run_workflow(
    db: Session, *, goal: str, agent_keys: list[str], mode: str,
    context: Optional[dict] = None, current_user: Optional[User] = None,
) -> AgentWorkflow:
    """
    Synchronous (blocking) end-to-end helper, kept for callers that
    genuinely want to await full completion in-process (e.g. tests,
    scripts, or a future Celery task). The HTTP route no longer uses this
    directly — see validate_and_create_workflow() + execute_workflow_background().
    """
    workflow = validate_and_create_workflow(
        db, goal=goal, agent_keys=agent_keys, mode=mode, context=context, current_user=current_user,
    )
    workflow.status = AgentExecutionStatus.running
    workflow.started_at = datetime.now(timezone.utc)
    db.commit()

    write_audit_log(
        db, action="workflow_execute", status="success", user_id=getattr(current_user, "id", None),
        resource=f"workflow:{workflow.id}", detail=f"mode={mode} agents={workflow.agent_keys}",
    )

    try:
        await _run_workflow_body(db, workflow, current_user)
        db.refresh(workflow)
        return workflow
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_execution_failed workflow_id=%s", workflow.id)
        db.refresh(workflow)
        workflow.status = AgentExecutionStatus.failed
        workflow.completed_at = datetime.now(timezone.utc)
        db.commit()
        write_audit_log(
            db, action="workflow_execute", status="failure", user_id=getattr(current_user, "id", None),
            resource=f"workflow:{workflow.id}", detail=str(exc),
        )
        return workflow


def get_workflow_executions(db: Session, workflow_id: str) -> list[AgentExecution]:
    return (
        db.query(AgentExecution)
        .filter(AgentExecution.workflow_id == workflow_id)
        .order_by(AgentExecution.created_at.asc())
        .all()
    )