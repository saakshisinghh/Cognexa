"""
apps/api/agents/base_agent.py

Phase 5 — BaseAgent: the shared LangGraph StateGraph framework every
concrete agent (RCA, Predictive Maintenance, Compliance, Lessons Learned)
is built from.

Every agent graph follows the same node sequence, per the Phase 5 spec:

    Planner -> Retriever -> Knowledge Graph Query -> Tool Executor
             -> Reasoner -> Validator -> Response Generator

with a bounded retry loop (Validator -> Retriever) governed by
`max_retries`, and every node appending to `execution_history` /
`reasoning` / `errors` so the full run is inspectable by the frontend
Agent Console (ToolCallTimeline / ExecutionLogs / WorkflowGraph).

Concrete agents customize behavior by overriding a small set of hook
methods (capabilities, system prompt, structured-output synthesis)
rather than re-implementing graph wiring — this is the template method
pattern applied to a LangGraph StateGraph.

Checkpointing: each execution's state is checkpointed via LangGraph's
in-memory `MemorySaver`, keyed by `execution_id` (used as `thread_id`).
This gives resumability/inspectability WITHIN a single running process
for the lifetime of an execution — it is intentionally not a durable
cross-restart store (that would be long-term memory, out of scope for
Phase 5; see agents/memory.py for the Redis-backed short-term store used
for cross-request session memory).
"""
from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from apps.api.agents.state import AgentState
from apps.api.agents.planner import generate_plan, ExecutionPlan
from apps.api.agents.memory import ExecutionMemory
from apps.api.agents.tools import execute_tool, list_tools, ToolOutput
from apps.api.services.llm_gateway import complete_response, LLMUnavailableError
from apps.api.schemas.retrieval import RetrievedChunk
from apps.api.services.retrieval.confidence_engine import compute_confidence
from apps.api.schemas.confidence import ConflictFlag

logger = logging.getLogger("indusmind.agents.base")

_RETRIEVAL_TOOLS = {"semantic_search", "hybrid_search", "rag_retrieval", "compliance_search", "document_reader"}
_GRAPH_TOOLS = {"knowledge_graph_query"}
# everything else registered in tools.ALL_TOOLS is routed to the generic tool executor


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseAgent(ABC):
    """
    Template-method base class for all Phase 5 agents.

    Subclasses MUST set:
        agent_id, name, description, version, prompt_file, capabilities

    Subclasses MAY override:
        build_structured_output(state) -> dict
            Agent-specific structured payload (e.g. ranked root causes,
            maintenance schedule, compliance report, lessons summary).
    """

    agent_id: str
    name: str
    description: str
    version: str = "1.0.0"
    prompt_file: str = "rca"           # matches prompts/agents/{prompt_file}.md
    capabilities: list[str] = []       # subset of tools.ALL_TOOLS this agent may use
    max_retries: int = 1

    def __init__(self):
        self._checkpointer = MemorySaver()
        self._graph = self._build_graph()
        # Live DB sessions are deliberately kept OUT of AgentState (and thus
        # out of LangGraph's checkpointer) because MemorySaver's serializer
        # cannot safely round-trip a SQLAlchemy Session. Instead they're
        # tracked per-execution here and looked up by node methods via
        # execution_id, then discarded when the run completes.
        self._active_dbs: dict[str, Session] = {}

    def _get_db(self, state: AgentState) -> Session:
        return self._active_dbs[state["execution_id"]]

    # ────────────────────────────────────────────────────────────────
    # Graph construction (shared by every agent)
    # ────────────────────────────────────────────────────────────────

    def _build_graph(self):
        graph = StateGraph(AgentState)

        graph.add_node("planner", self._planner_node)
        graph.add_node("retriever", self._retriever_node)
        graph.add_node("graph_query", self._graph_query_node)
        graph.add_node("tool_executor", self._tool_executor_node)
        graph.add_node("reasoner", self._reasoner_node)
        graph.add_node("validator", self._validator_node)
        graph.add_node("response_generator", self._response_generator_node)

        graph.set_entry_point("planner")
        graph.add_edge("planner", "retriever")
        graph.add_edge("retriever", "graph_query")
        graph.add_edge("graph_query", "tool_executor")
        graph.add_edge("tool_executor", "reasoner")
        graph.add_edge("reasoner", "validator")
        graph.add_conditional_edges(
            "validator",
            self._route_after_validation,
            {"retry": "retriever", "proceed": "response_generator"},
        )
        graph.add_edge("response_generator", END)

        return graph.compile(checkpointer=self._checkpointer)

    def _route_after_validation(self, state: AgentState) -> str:
        if state.get("completion_status") == "needs_more_evidence" and \
                state.get("retry_count", 0) < state.get("max_retries", self.max_retries):
            return "retry"
        return "proceed"

    # ────────────────────────────────────────────────────────────────
    # Node: Planner
    # ────────────────────────────────────────────────────────────────

    async def _planner_node(self, state: AgentState) -> dict:
        start = time.monotonic()
        available_tools = [t for t in list_tools() if t["name"] in self.capabilities]
        plan: ExecutionPlan = await generate_plan(
            goal=state["goal"], agent_name=self.name,
            available_tools=available_tools, context=state.get("context", {}),
        )
        duration = round((time.monotonic() - start) * 1000, 2)
        return {
            "plan": {
                "goal_summary": plan.goal_summary,
                "task_type": plan.task_type,
                "tasks": [t.__dict__ for t in plan.tasks],
                "estimated_confidence": plan.estimated_confidence,
            },
            "task_type": plan.task_type,
            "current_step": "planner",
            "retry_count": state.get("retry_count", 0),
            "max_retries": state.get("max_retries", self.max_retries),
            "execution_history": [{
                "step": "planner", "status": "completed",
                "detail": f"Generated {len(plan.tasks)}-task plan (type={plan.task_type})",
                "timestamp": _now(), "duration_ms": duration,
            }],
            "reasoning": [{
                "step": "planner", "thought": plan.goal_summary, "timestamp": _now(),
            }],
        }

    # ────────────────────────────────────────────────────────────────
    # Node: Retriever (semantic_search / hybrid_search / rag_retrieval /
    # compliance_search / document_reader tasks from the plan)
    # ────────────────────────────────────────────────────────────────

    async def _retriever_node(self, state: AgentState) -> dict:
        db = self._get_db(state)
        tasks = state.get("plan", {}).get("tasks", [])
        retrieved: list[dict] = []
        sources: list[dict] = []
        history: list[dict] = []

        for task in tasks:
            tool_name = task.get("tool")
            if tool_name not in _RETRIEVAL_TOOLS:
                continue
            start = time.monotonic()
            result: ToolOutput = await execute_tool(tool_name, task.get("tool_input") or {}, db=db)
            duration = round((time.monotonic() - start) * 1000, 2)
            history.append({
                "step": f"retriever:{tool_name}", "status": "completed" if result.ok else "failed",
                "detail": task.get("task", ""), "timestamp": _now(), "duration_ms": duration,
            })
            if result.ok:
                payload = result.data if isinstance(result.data, list) else [result.data]
                retrieved.extend(p for p in payload if p is not None)
                sources.extend(result.source_refs)
            else:
                logger.warning("retriever_task_failed tool=%s error=%s", tool_name, result.error)

        return {
            "current_step": "retriever",
            "retrieved_documents": retrieved,
            "sources": sources,
            "execution_history": history,
        }

    # ────────────────────────────────────────────────────────────────
    # Node: Knowledge Graph Query
    # ────────────────────────────────────────────────────────────────

    async def _graph_query_node(self, state: AgentState) -> dict:
        db = self._get_db(state)
        tasks = state.get("plan", {}).get("tasks", [])
        graph_results: list[dict] = []
        history: list[dict] = []

        for task in tasks:
            if task.get("tool") not in _GRAPH_TOOLS:
                continue
            start = time.monotonic()
            result: ToolOutput = await execute_tool("knowledge_graph_query", task.get("tool_input") or {}, db=db)
            duration = round((time.monotonic() - start) * 1000, 2)
            history.append({
                "step": "graph_query", "status": "completed" if result.ok else "failed",
                "detail": task.get("task", ""), "timestamp": _now(), "duration_ms": duration,
            })
            if result.ok and result.data is not None:
                graph_results.append(result.data if isinstance(result.data, dict) else {"result": result.data})

        return {"current_step": "graph_query", "graph_results": graph_results, "execution_history": history}

    # ────────────────────────────────────────────────────────────────
    # Node: Tool Executor (everything else: asset_lookup, incident_search,
    # maintenance_history, conversation_history, audit_lookup, prompt_library)
    # ────────────────────────────────────────────────────────────────

    async def _tool_executor_node(self, state: AgentState) -> dict:
        db = self._get_db(state)
        tasks = state.get("plan", {}).get("tasks", [])
        tool_results: list[dict] = []
        history: list[dict] = []
        errors: list[dict] = []

        for task in tasks:
            tool_name = task.get("tool")
            if not tool_name or tool_name in _RETRIEVAL_TOOLS or tool_name in _GRAPH_TOOLS:
                continue
            start = time.monotonic()
            result: ToolOutput = await execute_tool(tool_name, task.get("tool_input") or {}, db=db)
            duration = round((time.monotonic() - start) * 1000, 2)
            tool_results.append({
                "tool_name": tool_name, "input": task.get("tool_input") or {},
                "output": result.data, "ok": result.ok, "error": result.error, "duration_ms": duration,
            })
            history.append({
                "step": f"tool:{tool_name}", "status": "completed" if result.ok else "failed",
                "detail": task.get("task", ""), "timestamp": _now(), "duration_ms": duration,
            })
            if not result.ok:
                errors.append({"node": "tool_executor", "message": f"{tool_name}: {result.error}",
                                "timestamp": _now(), "recoverable": True})

        return {
            "current_step": "tool_executor", "tool_results": tool_results,
            "execution_history": history, "errors": errors,
        }

    # ────────────────────────────────────────────────────────────────
    # Node: Reasoner
    # ────────────────────────────────────────────────────────────────

    async def _reasoner_node(self, state: AgentState) -> dict:
        start = time.monotonic()
        evidence_summary = {
            "retrieved_documents_count": len(state.get("retrieved_documents", [])),
            "graph_results_count": len(state.get("graph_results", [])),
            "tool_results_count": len(state.get("tool_results", [])),
        }
        prompt = (
            f"Goal: {state['goal']}\n"
            f"Evidence gathered: {json.dumps(evidence_summary)}\n"
            "In 2-3 sentences, reason about whether this evidence is sufficient to answer the goal, "
            "and note any gaps. Respond with plain text only."
        )
        try:
            thought, _in_tok, _out_tok = await complete_response(
                [{"role": "system", "content": f"You are the reasoning module of {self.name}."},
                 {"role": "user", "content": prompt}]
            )
        except LLMUnavailableError as exc:
            thought = f"(reasoning LLM unavailable: {exc}) proceeding with gathered evidence."

        duration = round((time.monotonic() - start) * 1000, 2)
        return {
            "current_step": "reasoner",
            "reasoning": [{"step": "reasoner", "thought": thought.strip(), "timestamp": _now()}],
            "execution_history": [{
                "step": "reasoner", "status": "completed", "detail": "Synthesized evidence sufficiency assessment",
                "timestamp": _now(), "duration_ms": duration,
            }],
        }

    # ────────────────────────────────────────────────────────────────
    # Node: Validator
    # ────────────────────────────────────────────────────────────────

    async def _validator_node(self, state: AgentState) -> dict:
        total_evidence = (
            len(state.get("retrieved_documents", []))
            + len(state.get("graph_results", []))
            + len(state.get("tool_results", []))
        )
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", self.max_retries)

        if total_evidence == 0 and retry_count < max_retries:
            status = "needs_more_evidence"
        else:
            status = "validated"

        return {
            "current_step": "validator",
            "completion_status": status,
            "retry_count": retry_count + 1 if status == "needs_more_evidence" else retry_count,
            "execution_history": [{
                "step": "validator", "status": "completed",
                "detail": f"total_evidence={total_evidence} status={status}",
                "timestamp": _now(), "duration_ms": None,
            }],
        }

    # ────────────────────────────────────────────────────────────────
    # Node: Response Generator
    # ────────────────────────────────────────────────────────────────

    async def _response_generator_node(self, state: AgentState) -> dict:
        start = time.monotonic()
        chunks = self._reconstruct_chunks(state.get("retrieved_documents", []))
        confidence = None
        conflicts: list[ConflictFlag] = []
        if chunks:
            confidence_result = compute_confidence(
                final_chunks=chunks, conflicts=conflicts,
                graph_chunk_count=0, graph_corroborates=True,
            )
            confidence = confidence_result.model_dump(mode="json")
        else:
            confidence = self._heuristic_confidence(state)

        answer = await self._synthesize_answer(state, chunks)
        structured_output = self.build_structured_output(state)

        duration = round((time.monotonic() - start) * 1000, 2)
        return {
            "current_step": "response_generator",
            "answer": answer,
            "confidence": confidence,
            "structured_output": structured_output,
            "completion_status": "completed",
            "execution_history": [{
                "step": "response_generator", "status": "completed",
                "detail": "Final answer synthesized", "timestamp": _now(), "duration_ms": duration,
            }],
        }

    # ────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _reconstruct_chunks(retrieved_documents: list[dict]) -> list[RetrievedChunk]:
        chunks: list[RetrievedChunk] = []
        for doc in retrieved_documents:
            if not isinstance(doc, dict) or "chunk_id" not in doc:
                continue
            try:
                chunks.append(RetrievedChunk(**doc))
            except Exception:  # noqa: BLE001 — tolerate partial/foreign shapes
                continue
        return chunks

    @staticmethod
    def _heuristic_confidence(state: AgentState) -> dict:
        tool_results = state.get("tool_results", [])
        ok_count = sum(1 for t in tool_results if t.get("ok"))
        total = max(len(tool_results), 1)
        ratio = ok_count / total
        level = "high" if ratio >= 0.8 and total >= 2 else "medium" if ratio >= 0.4 else "low"
        return {
            "level": level, "raw_score": round(ratio, 2),
            "factors": {"supporting_document_count": 0, "avg_retrieval_score": 0.0,
                        "graph_consistency_score": 1.0 if not state.get("errors") else 0.5,
                        "citation_count": len(state.get("sources", [])),
                        "avg_trust_score": 0.5, "has_conflict": False, "conflict_penalty_applied": 0.0},
            "explanation": f"Heuristic confidence from tool success ratio ({ok_count}/{total} tools succeeded).",
        }

    def _load_prompt(self) -> str:
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "prompts", "agents", f"{self.prompt_file}.md")
        path = os.path.normpath(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("agent_prompt_missing agent=%s path=%s", self.agent_id, path)
            return f"You are {self.name}. {self.description}"

    async def _synthesize_answer(self, state: AgentState, chunks: list[RetrievedChunk]) -> str:
        context_block = "\n\n".join(
            f"[SOURCE {i+1}: {c.document_title}]\n{c.content[:600]}" for i, c in enumerate(chunks[:8])
        ) or "[No retrieved document chunks — rely on structured tool results below.]"

        tool_summary = json.dumps(
            [{"tool": t["tool_name"], "ok": t["ok"], "output": _truncate(t["output"])}
             for t in state.get("tool_results", [])][:10],
            default=str,
        )
        graph_summary = json.dumps(state.get("graph_results", [])[:5], default=str)
        reasoning_summary = "\n".join(r["thought"] for r in state.get("reasoning", []))

        system_prompt = self._load_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"GOAL: {state['goal']}\n\n"
                f"RETRIEVED CONTEXT:\n{context_block}\n\n"
                f"GRAPH RESULTS:\n{graph_summary}\n\n"
                f"TOOL RESULTS:\n{tool_summary}\n\n"
                f"PRIOR REASONING:\n{reasoning_summary}\n\n"
                "Produce your final answer now, following the response format defined in your system prompt."
            )},
        ]
        try:
            answer, _in_tok, _out_tok = await complete_response(messages)
            return answer.strip()
        except LLMUnavailableError as exc:
            logger.error("response_generator_llm_failed agent=%s error=%s", self.agent_id, exc)
            return (
                "The language model backend is currently unavailable, so a narrative answer "
                "could not be generated. Structured findings from tools and retrieval are "
                "available in the execution results below."
            )

    def build_structured_output(self, state: AgentState) -> dict:
        """
        Default structured output — subclasses override to shape
        agent-specific payloads (ranked causes, maintenance plan, etc).
        """
        return {
            "task_type": state.get("task_type"),
            "evidence_counts": {
                "documents": len(state.get("retrieved_documents", [])),
                "graph_results": len(state.get("graph_results", [])),
                "tool_results": len(state.get("tool_results", [])),
            },
        }

    # ────────────────────────────────────────────────────────────────
    # Public execution API
    # ────────────────────────────────────────────────────────────────

    def initial_state(
        self, execution_id: str, goal: str, db: Session,
        user_id: Optional[str] = None, context: Optional[dict] = None,
    ) -> AgentState:
        ctx = dict(context or {})
        return {
            "execution_id": execution_id, "agent_id": self.agent_id,
            "agent_version": self.version, "user_id": user_id,
            "goal": goal, "task_type": "", "plan": {},
            "context": ctx, "conversation": [],
            "retrieved_documents": [], "graph_results": [], "tool_results": [],
            "current_step": "queued", "reasoning": [], "execution_history": [], "errors": [],
            "retry_count": 0, "max_retries": self.max_retries,
            "answer": "", "sources": [], "confidence": {}, "structured_output": {},
            "completion_status": "running",
        }

    async def run(self, execution_id: str, goal: str, db: Session,
                   user_id: Optional[str] = None, context: Optional[dict] = None) -> AgentState:
        """Synchronous (non-streaming) full execution — used by agent_executor."""
        state = self.initial_state(execution_id, goal, db, user_id, context)
        config = {"configurable": {"thread_id": execution_id}}
        self._active_dbs[execution_id] = db
        try:
            final_state = await self._graph.ainvoke(state, config=config)
        finally:
            self._active_dbs.pop(execution_id, None)
        return final_state

    async def stream(self, execution_id: str, goal: str, db: Session,
                      user_id: Optional[str] = None, context: Optional[dict] = None
                      ) -> AsyncGenerator[dict, None]:
        """
        Streams one event per completed LangGraph node — consumed by
        routers/agents.py to power the live streaming Agent Console view.
        """
        state = self.initial_state(execution_id, goal, db, user_id, context)
        config = {"configurable": {"thread_id": execution_id}}
        self._active_dbs[execution_id] = db
        try:
            async for event in self._graph.astream(state, config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    yield {"node": node_name, "output": _strip_internal(node_output)}
        finally:
            self._active_dbs.pop(execution_id, None)


def _truncate(value: Any, max_len: int = 500) -> Any:
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "…"
    return value


def _strip_internal(payload: dict) -> dict:
    """Removes non-serializable internal keys (like the raw db Session) before
    an update is emitted over SSE."""
    if not isinstance(payload, dict):
        return payload
    cleaned = dict(payload)
    ctx = cleaned.get("context")
    if isinstance(ctx, dict) and "_db" in ctx:
        ctx = {k: v for k, v in ctx.items() if k != "_db"}
        cleaned["context"] = ctx
    return cleaned
