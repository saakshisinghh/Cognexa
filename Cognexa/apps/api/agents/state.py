"""
apps/api/agents/state.py

Phase 5 — Agentic AI Platform.

Defines the shared LangGraph state schema used by every agent's
StateGraph. This is the single source of truth for "what an agent
execution looks like while it's running" — every node in every agent
graph (planner, retriever, graph-query, tool-executor, reasoner,
validator, response-generator) reads from and writes to this state.

Design notes
------------
- Implemented as a TypedDict (not a Pydantic model) because LangGraph's
  StateGraph applies reducers per-key on partial dict returns from nodes;
  TypedDict is the documented, idiomatic shape for this.
- Reducers (via `Annotated[..., operator.add]` / custom reducers) are used
  for fields that accumulate across nodes (execution_history, reasoning,
  errors, retrieved_documents, graph_results, tool_results) so nodes can
  return only the *new* items and LangGraph merges them, rather than every
  node needing the full running list.
- This state is intentionally SHORT-TERM / EXECUTION-SCOPED. It lives only
  for the lifetime of one agent run (checkpointed via LangGraph's
  MemorySaver, keyed by execution_id as the thread_id). Long-term
  cross-execution organizational memory is explicitly out of scope for
  Phase 5 (reserved for Phase 6's Temporal Memory Engine).
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Optional, TypedDict


def _merge_dicts(left: dict, right: dict) -> dict:
    """Reducer for dict-valued state fields: shallow-merge, right wins."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class ExecutionStep(TypedDict):
    """One entry in the execution timeline / log, surfaced to the frontend
    ToolCallTimeline and ExecutionLogs components."""
    step: str                  # e.g. "planner", "retriever", "tool:semantic_search"
    status: str                 # "started" | "completed" | "failed" | "retried"
    detail: str
    timestamp: str               # ISO 8601
    duration_ms: Optional[float]


class ReasoningTrace(TypedDict):
    """A single reasoning entry produced by the Reasoner node."""
    step: str
    thought: str
    timestamp: str


class ToolResult(TypedDict):
    tool_name: str
    input: dict
    output: Any
    ok: bool
    error: Optional[str]
    duration_ms: float


class AgentError(TypedDict):
    node: str
    message: str
    timestamp: str
    recoverable: bool


class AgentState(TypedDict, total=False):
    """
    Shared execution state threaded through every node of an agent's
    LangGraph StateGraph.

    Required-by-spec fields (verbatim from the Phase 5 brief):
        Goal, Context, Conversation, Retrieved Documents, Graph Results,
        Tool Results, Current Step, Reasoning, Execution History, Errors,
        Confidence, Completion Status.
    """

    # ── Identity ─────────────────────────────────────────────────────────
    execution_id: str
    agent_id: str
    agent_version: str
    user_id: Optional[str]

    # ── Goal ─────────────────────────────────────────────────────────────
    goal: str                        # the user's raw request / task
    task_type: str                    # agent-specific classification of the goal
    plan: dict                        # output of the Planner node

    # ── Context ──────────────────────────────────────────────────────────
    context: Annotated[dict, _merge_dicts]              # asset_id, plant_id, filters, etc.
    conversation: Annotated[list[dict], operator.add]    # [{role, content}, ...]

    # ── Retrieval ────────────────────────────────────────────────────────
    retrieved_documents: Annotated[list[dict], operator.add]
    graph_results: Annotated[list[dict], operator.add]
    tool_results: Annotated[list[ToolResult], operator.add]

    # ── Reasoning / control flow ────────────────────────────────────────
    current_step: str
    reasoning: Annotated[list[ReasoningTrace], operator.add]
    execution_history: Annotated[list[ExecutionStep], operator.add]
    errors: Annotated[list[AgentError], operator.add]
    retry_count: int
    max_retries: int

    # ── Output ───────────────────────────────────────────────────────────
    answer: str
    sources: Annotated[list[dict], operator.add]
    confidence: dict                  # {level, raw_score, factors, explanation}
    structured_output: dict           # agent-specific structured result payload
    completion_status: str            # "running" | "completed" | "failed" | "cancelled"
