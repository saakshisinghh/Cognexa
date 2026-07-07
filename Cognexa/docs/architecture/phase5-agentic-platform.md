# Phase 5 — Agentic AI Platform

INDUS MIND grows from an Industrial Copilot (Phase 4: one request, one
retrieval pipeline, one answer) into an **Agentic AI Platform**: four
specialist agents that plan multi-step investigations, call tools,
query the knowledge graph, retrieve documents, reason over evidence,
and produce ranked, cited, confidence-scored answers — all inside the
existing FastAPI monolith, reusing every Phase 1-4 service rather than
duplicating them.

This document covers the architecture, execution flow, tool system,
workflow engine, and API surface added in Phase 5. It assumes
familiarity with the Phase 1-4 architecture already documented
elsewhere in this repo.

---

## 1. Why LangGraph, and why this shape

Each agent is a compiled [LangGraph](https://langchain-ai.github.io/langgraph/)
`StateGraph` over a shared `AgentState` (`apps/api/agents/state.py`).
Every agent follows the same seven-node sequence, per the Phase 5 spec:

```
Planner → Retriever → Knowledge Graph Query → Tool Executor
        → Reasoner → Validator → Response Generator
                          ↑___________________|
                       (bounded retry loop)
```

- **Planner** — turns the user's goal into an ordered task list, each
  task optionally bound to a tool. Uses the existing OpenAI-compatible
  LLM gateway with constrained JSON prompting (see §3 — no
  provider-specific function calling, so this works against small
  local Ollama models as well as hosted OpenAI-compatible endpoints).
- **Retriever** — executes plan tasks bound to retrieval tools
  (`semantic_search`, `hybrid_search`, `rag_retrieval`,
  `compliance_search`, `document_reader`).
- **Knowledge Graph Query** — executes plan tasks bound to
  `knowledge_graph_query` (Neo4j, via the existing `GraphService`).
- **Tool Executor** — executes every other plan task (asset/incident
  lookups, maintenance history, conversation history, audit lookup,
  prompt library).
- **Reasoner** — asks the LLM to assess evidence sufficiency in 2-3
  sentences; this becomes part of the final synthesis prompt and the
  visible "reasoning trace" in the frontend.
- **Validator** — if literally zero evidence was gathered and the
  agent hasn't exhausted `max_retries`, routes back to the Retriever
  for another attempt; otherwise proceeds.
- **Response Generator** — synthesizes the final answer (via the
  agent's `prompts/agents/{name}.md` system prompt), computes
  confidence (reusing Phase 4's `confidence_engine` when retrieval
  chunks are available, falling back to a tool-success heuristic
  otherwise), and builds the agent-specific `structured_output`.

Every node appends to `execution_history` / `reasoning` / `errors`
(reducer-merged via `Annotated[..., operator.add]` on `AgentState`), so
the full run is inspectable step-by-step by the frontend's
`ToolCallTimeline`, `ExecutionLogs`, and `WorkflowGraph` components —
this was a first-class design goal, not an afterthought.

### Checkpointing scope

Each execution is checkpointed via LangGraph's in-memory `MemorySaver`,
keyed by `execution_id` as the `thread_id`. This is intentionally
**short-term and process-local** — it gives resumability/inspectability
for the lifetime of one running execution, not a durable cross-restart
store. Durable history (for the Execution History / Logs API) is
written separately to Postgres (`AgentExecution`, `AgentExecutionStep`)
by `services/agent_executor.py` once each node completes.

**Design note — DB sessions are kept out of `AgentState`.** An earlier
draft carried the SQLAlchemy `Session` inside `state["context"]["_db"]`
for convenience. This was corrected: LangGraph's checkpointer
serializes state snapshots, and a live `Session` cannot round-trip
through that safely. Sessions are now tracked per-execution in
`BaseAgent._active_dbs` (keyed by `execution_id`) and looked up by node
methods via `self._get_db(state)`, never touching checkpointed state.

---

## 2. Agent capability matrix

| Agent | agent_id | Tools (capabilities) | Structured output |
|---|---|---|---|
| Root Cause Analysis | `rca_agent` | incident_search, knowledge_graph_query, semantic_search, hybrid_search, rag_retrieval, maintenance_history, asset_lookup, document_reader | ranked causes, similar incidents, maintenance context |
| Predictive Maintenance | `maintenance_agent` | asset_lookup, maintenance_history, incident_search, document_reader, knowledge_graph_query, semantic_search, hybrid_search, rag_retrieval | asset info, maintenance history, similar-asset graph relationships |
| Compliance | `compliance_agent` | compliance_search, document_reader, asset_lookup, audit_lookup (sensitive), knowledge_graph_query, hybrid_search, rag_retrieval | compliance docs reviewed, audit entries |
| Lessons Learned | `lessons_agent` | incident_search, knowledge_graph_query, semantic_search, hybrid_search, rag_retrieval, document_reader, conversation_history | incidents analyzed, recurring patterns (≥2 corroborating instances required) |

Every agent is a template-method subclass of `BaseAgent`
(`apps/api/agents/base_agent.py`) — a concrete agent only declares its
identity (`agent_id`, `name`, `description`, `version`,
`prompt_file`, `capabilities`, `max_retries`) and overrides
`build_structured_output(state)` to shape its result payload. All graph
wiring, retrieval/tool dispatch, confidence scoring, and answer
synthesis are inherited, not reimplemented per agent.

---

## 3. Tool system

Twelve reusable tools live in `apps/api/agents/tools.py`
(`ALL_TOOLS` registry). **Every tool is a thin adapter over an existing
Phase 1-4 service — none reimplement retrieval, graph, or search
logic:**

| Tool | Wraps |
|---|---|
| `semantic_search` | `services.retrieval.vector_retrieve` |
| `knowledge_graph_query` | `services.graph.GraphService` (search / asset_graph / similar_assets / expand_node) |
| `document_reader` | `models.Document` (extracted_text) |
| `asset_lookup` | `models.Asset` |
| `incident_search` | `models.incident.Incident` |
| `compliance_search` | BM25 + vector fused, filtered to `document_type="compliance"` |
| `maintenance_history` | `Incident` + `Document` joined by `asset_id` |
| `rag_retrieval` | `services.retrieval.run_triple_retrieval` (full Phase 4 pipeline) |
| `hybrid_search` | BM25 + vector fused (no graph) — faster than `rag_retrieval` |
| `prompt_library` | `prompts/agents/*.md` |
| `conversation_history` | `models.ConversationSession`, `models.QueryHistory` |
| `audit_lookup` | `models.AuditLog` — **sensitive**, restricted to admin/engineer roles |

### Tool-calling contract

Tool selection is **not** done via provider-specific function calling.
The Planner asks the LLM to return a JSON task list naming tools by
string (`agents/planner.py::_build_planner_prompt`), which is validated
against the agent's `capabilities` before execution. This was a
deliberate choice: the platform must work against small local Ollama
models that do not reliably support native tool-calling, as well as
hosted OpenAI-compatible backends — constrained JSON prompting is
portable across both.

### Permission enforcement

`tools.execute_tool()` checks `Tool.sensitive` against the calling
user's role **before** running the tool body, regardless of what the
Planner proposed — a compromised or hallucinated plan cannot bypass
RBAC on `audit_lookup`.

---

## 4. Multi-agent collaboration

`services/workflow_engine.py` implements all four collaboration
patterns from the spec, layered **on top of** (not duplicating)
`services/agent_executor.py`'s single-agent execution primitive:

- **Single** — one agent, one execution (handled directly by
  `agent_executor.execute_agent`).
- **Sequential** — agents run one after another; each subsequent
  agent receives prior agents' answers as `prior_agent_findings` in
  its `context` (the handoff mechanism).
- **Parallel** — agents run concurrently via `asyncio.gather` against
  the same goal/context, independent of each other.
- **Supervisor** — an LLM supervisor reads the goal and the caller's
  authorized agent set, decides which agents to invoke and in what
  order (bounded to that authorized set — the supervisor cannot invoke
  an agent the caller didn't include), then executes sequentially with
  handoff, identical to the Sequential path.

**Shared context / shared memory** — all agents in a workflow read
from and write to the same `AgentWorkflow.shared_context` dict, which
is passed into each participating agent's `context`. This is distinct
from each agent's own execution-scoped `ExecutionMemory`
(`agents/memory.py`), which remains private to that single run.

**Conflict resolution** — after all participating agents complete, a
lightweight LLM-based reconciliation step (`_detect_conflicts`)
compares their answers and confidence levels and flags genuine
factual contradictions (not just differing emphasis) rather than
silently picking one agent's answer. Detected conflicts are stored on
`AgentWorkflow.conflicts` and surfaced in the frontend's
`WorkflowGraph` side panel.

---

## 5. Execution lifecycle, security, and observability

`services/agent_executor.py` owns the full lifecycle of a single
execution:

1. **Permission check** — resolves the agent through
   `agent_registry.get_agent()`, which returns `None` for disabled
   agents (a disabled agent cannot be run even if its `agent_id` is
   guessed).
2. **Rate limiting** — a Redis fixed-window limiter
   (`agent:ratelimit:{user_id}`, 10 executions / 60s) guards against
   runaway loops; a Redis outage fails open (logged, not blocking)
   rather than taking down agent execution.
3. **Persistence** — every execution is a row in `AgentExecution`
   (goal, plan, answer, structured_output, confidence, sources,
   errors, timing), with one `AgentExecutionStep` row per LangGraph
   node/tool step — this is what backs the Execution History,
   Execution Detail, and Execution Logs APIs.
4. **Audit** — every execution and workflow run, cancellation, and
   agent enable/disable is written to the existing Phase 2
   `AuditLog` table via `services.audit.write_audit_log`, using four
   new `AuditAction` values added in `migrations/versions/
   phase5_agents.py` (`agent_execute`, `agent_cancel`, `agent_enable`,
   `agent_disable`, `workflow_execute`).
5. **Cancellation** — cooperative: `POST /agents/{key}/cancel/{id}`
   sets `AgentExecution.cancel_requested`; the streaming path checks
   this after every node and stops promptly rather than killing the
   process mid-node.

### Agent Registry (`services/agent_registry.py`)

Agents are registered **dynamically** at startup
(`main.py`'s lifespan calls `sync_agent_definitions()`), which
upserts one `AgentDefinition` row per agent found in
`apps.api.agents.__init__`. This table is the discoverability/admin
surface (list, enable/disable, health status); the actual executable
`BaseAgent` singletons remain in-process (`_AGENTS` dict) — the DB row
is not itself invokable, avoiding any temptation to reconstruct agent
behavior from persisted config.

Health checks (`GET /agents/health`, `GET /agents/{key}/health`) are
deliberately lightweight: they confirm the agent's LangGraph compiled
and its prompt template loads, **without** invoking the LLM or any
retrieval backend — that's what running the agent is for.

---

## 6. Database schema (migration `phase5_agents`)

New tables, chained after `002_phase4`:

- **`agent_definitions`** — registry row per agent (enabled, version,
  capabilities, health).
- **`agent_workflows`** — one row per multi-agent collaboration run.
- **`agent_executions`** — one row per agent run (goal, plan, answer,
  confidence, timing, `workflow_id` FK for workflow membership).
- **`agent_execution_steps`** — one row per LangGraph node/tool step
  within an execution (durable mirror of `AgentState.execution_history`).

The migration also extends the existing native Postgres `auditaction`
enum with `agent_execute`, `agent_cancel`, `agent_enable`,
`agent_disable`, `workflow_execute` via `ALTER TYPE ... ADD VALUE`.
Run it with the project's existing Alembic setup:

```bash
cd apps/api
alembic upgrade head
```

---

## 7. Frontend — Agent Console

Added under `apps/web/app/agents/` and `apps/web/components/agents/`,
reusing the existing design tokens, `AppLayout`, and both API-client
conventions already in the codebase (`lib/api.ts` axios instance for
standard requests, raw `fetch` + `ReadableStream` for the SSE run
endpoint — the same pattern Phase 4's Copilot streaming already
established on the backend).

| Page | Purpose |
|---|---|
| `/agents` | Agent Catalog (health, enable/disable for admins) + inline run panel |
| `/agents/history` | Searchable/filterable execution history |
| `/agents/executions/[id]` | Durable execution detail (timeline, logs, structured output, sources) |
| `/agents/workflows` | Configure and launch a multi-agent workflow |
| `/agents/workflows/[id]` | React Flow visualization of workflow agents, statuses, and conflicts |

| Component | Purpose |
|---|---|
| `AgentCard` | Catalog tile: health, capabilities, run / enable-disable |
| `AgentChat` | Live SSE-streaming run interface |
| `AgentExecution` | Composed detail view: goal, confidence bar, answer, sources, tabs |
| `ToolCallTimeline` | Visual step-by-step execution timeline |
| `ExecutionLogs` | Searchable/filterable raw log table |
| `WorkflowGraph` | React Flow graph of a multi-agent workflow, click-to-inspect |

---

## 8. What Phase 5 deliberately does NOT include

Per the Phase 5 brief, the following are explicitly out of scope and
were not implemented, even where adjacent:

- Temporal Memory Engine, Knowledge Decay, Knowledge Gap Detection,
  Knowledge Loss Prediction (Phase 6).
- Long-term organizational memory — `agents/memory.py` is
  intentionally short-term/execution-scoped only (24h TTL, Redis-backed
  with local fallback).
- Kubernetes, Kafka, microservice extraction, Terraform, a dedicated
  monitoring stack (Phase 7). Everything Phase 5 added lives inside the
  existing FastAPI monolith at `apps/api/`.
- Side-by-side multi-version agent execution — bumping an agent's
  `version` class attribute and restarting the API is how a new
  version is rolled out; there is no live A/B agent versioning.

---

## 9. Testing

`apps/api/tests/agents/` (52 tests): unit tests (state reducers,
`ExecutionMemory` Redis fallback, planner JSON extraction/fallback),
tool tests (registry completeness, sensitive-tool RBAC gating),
LangGraph/agent tests (graph compilation, full node-sequence execution,
retry-loop behavior, structured-output shape per agent), streaming
tests (event ordering, no DB-session leakage into SSE payloads,
`_active_dbs` cleanup), integration tests (real SQLAlchemy ORM models
against an in-memory SQLite DB — sequential/parallel/supervisor
workflows, handoff, conflict detection, disabled-agent exclusion), and
performance/orchestration-overhead tests (single-run overhead bound,
proof that parallel workflows are actually concurrent via
`asyncio.gather` rather than sequential awaits).

Run them with:

```bash
cd apps/api
pytest tests/agents/ -v
```
