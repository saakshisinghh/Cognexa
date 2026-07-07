"""
apps/api/agents/tools.py

Phase 5 — reusable agent tools.

CRITICAL DESIGN PRINCIPLE: every tool here is a thin adapter over an
EXISTING Phase 1-4 service. No retrieval, graph, or search logic is
duplicated — this module only adapts existing return shapes into a
uniform `ToolOutput` envelope that agent graphs can reason over and that
the frontend ToolCallTimeline can render generically.

Reused services (NOT reimplemented):
    - apps.api.services.retrieval (Phase 4 triple-retrieval pipeline:
      BM25 + vector + graph + RRF fusion + rerank + confidence)
    - apps.api.services.graph.GraphService (Phase 3 Neo4j wrapper)
    - apps.api.services.context_assembler (chunk -> citation formatting)
    - apps.api.models (Asset, Document, Incident, ConversationSession,
      QueryHistory, AuditLog — Phase 1-4 ORM models)

Tool-calling contract
----------------------
Each tool is registered as a `Tool` (name, description, input_schema,
async run(...)). The Planner/Reasoner select tools by NAME using
structured JSON output from the LLM (see agents/planner.py and
agents/base_agent.py) rather than relying on provider-specific function
calling — this keeps tool selection deterministic and portable across
any OpenAI-compatible backend (including small local Ollama models that
do not reliably support native tool-calling).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from apps.api.models import Asset, Document, User
from apps.api.models.incident import Incident
from apps.api.models.conversation import ConversationSession
from apps.api.models.query_history import QueryHistory
from apps.api.models.audit_log import AuditLog
from apps.api.schemas.retrieval import RetrievalFilters
from apps.api.services import retrieval as retrieval_svc
from apps.api.services.graph import GraphService

logger = logging.getLogger("indusmind.agents.tools")

_graph_service = GraphService()


@dataclass
class ToolOutput:
    ok: bool
    data: Any
    error: Optional[str] = None
    source_refs: list[dict] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    run: Callable[..., Awaitable[ToolOutput]]
    sensitive: bool = False  # sensitive tools are subject to extra RBAC checks


async def _timed(coro) -> tuple[Any, float]:
    start = time.monotonic()
    result = await coro
    return result, round((time.monotonic() - start) * 1000, 2)


def _chunk_to_ref(chunk) -> dict:
    return {
        "document_id": str(chunk.document_id),
        "document_title": chunk.document_title,
        "chunk_id": str(chunk.chunk_id),
        "excerpt": chunk.content[:300],
        "trust_score": chunk.trust_score,
        "page_number": chunk.page_number,
    }


# ════════════════════════════════════════════════════════════════════════
#  1. Semantic Search Tool — pure vector retrieval
# ════════════════════════════════════════════════════════════════════════

async def _semantic_search(input: dict, *, db: Session, **_) -> ToolOutput:
    query = input.get("query", "")
    top_k = int(input.get("top_k", 8))
    filters = RetrievalFilters(**input.get("filters", {}))
    try:
        (chunks, elapsed) = await _timed(
            retrieval_svc.vector_retrieve(query=query, top_k=top_k, filters=filters)
        )
        return ToolOutput(
            ok=True,
            data=[c.model_dump(mode="json") for c in chunks],
            source_refs=[_chunk_to_ref(c) for c in chunks],
            duration_ms=elapsed,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_search_tool_failed: %s", exc)
        return ToolOutput(ok=False, data=[], error=str(exc))


semantic_search_tool = Tool(
    name="semantic_search",
    description="Pure vector/semantic search over document chunks for a natural-language query.",
    input_schema={"query": "string", "top_k": "int (optional)", "filters": "RetrievalFilters (optional)"},
    run=_semantic_search,
)


# ════════════════════════════════════════════════════════════════════════
#  2. Knowledge Graph Tool — Neo4j queries via existing GraphService
# ════════════════════════════════════════════════════════════════════════

async def _knowledge_graph_query(input: dict, *, db: Session, **_) -> ToolOutput:
    mode = input.get("mode", "search")  # "search" | "asset_graph" | "similar_assets" | "expand_node"
    try:
        start = time.monotonic()
        if mode == "asset_graph":
            data = await asyncio.to_thread(
                _graph_service.get_asset_graph,
                input["asset_id"], input.get("depth", 1), input.get("limit", 100),
            )
        elif mode == "similar_assets":
            data = await asyncio.to_thread(
                _graph_service.similar_assets, input["asset_id"], input.get("limit", 10)
            )
        elif mode == "expand_node":
            data = await asyncio.to_thread(
                _graph_service.expand_node, input["node_id"],
                input.get("relationship_types"), input.get("limit", 50),
            )
        else:
            data = await asyncio.to_thread(
                _graph_service.search, input.get("query", ""), input.get("labels"), input.get("limit", 20)
            )
        elapsed = round((time.monotonic() - start) * 1000, 2)
        return ToolOutput(ok=True, data=data, duration_ms=elapsed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge_graph_tool_failed: %s", exc)
        return ToolOutput(ok=False, data=None, error=str(exc))


knowledge_graph_tool = Tool(
    name="knowledge_graph_query",
    description="Query the Neo4j industrial knowledge graph: node search, asset neighborhoods, similar assets.",
    input_schema={"mode": "search|asset_graph|similar_assets|expand_node", "query": "string (optional)",
                  "asset_id": "string (optional)", "node_id": "string (optional)"},
    run=_knowledge_graph_query,
)


# ════════════════════════════════════════════════════════════════════════
#  3. Document Reader Tool
# ════════════════════════════════════════════════════════════════════════

async def _document_reader(input: dict, *, db: Session, **_) -> ToolOutput:
    start = time.monotonic()
    doc_id = input.get("document_id")
    doc: Optional[Document] = db.query(Document).filter(Document.id == doc_id).first()
    elapsed = round((time.monotonic() - start) * 1000, 2)
    if not doc:
        return ToolOutput(ok=False, data=None, error=f"Document {doc_id} not found", duration_ms=elapsed)
    max_chars = int(input.get("max_chars", 4000))
    data = {
        "id": doc.id,
        "filename": doc.original_filename,
        "category": doc.category,
        "tags": doc.tags,
        "page_count": doc.page_count,
        "asset_id": doc.asset_id,
        "excerpt": (doc.extracted_text or "")[:max_chars],
    }
    return ToolOutput(
        ok=True, data=data,
        source_refs=[{"document_id": doc.id, "document_title": doc.original_filename, "excerpt": data["excerpt"][:300]}],
        duration_ms=elapsed,
    )


document_reader_tool = Tool(
    name="document_reader",
    description="Fetch a document's extracted text and metadata by document_id.",
    input_schema={"document_id": "string", "max_chars": "int (optional)"},
    run=_document_reader,
)


# ════════════════════════════════════════════════════════════════════════
#  4. Asset Lookup Tool
# ════════════════════════════════════════════════════════════════════════

async def _asset_lookup(input: dict, *, db: Session, **_) -> ToolOutput:
    start = time.monotonic()
    q = db.query(Asset)
    if input.get("asset_id"):
        q = q.filter(Asset.id == input["asset_id"])
    elif input.get("name"):
        q = q.filter(Asset.name.ilike(f"%{input['name']}%"))
    assets = q.limit(int(input.get("limit", 10))).all()
    elapsed = round((time.monotonic() - start) * 1000, 2)
    data = [
        {
            "id": a.id, "name": a.name, "asset_type": a.asset_type,
            "location": a.location, "health_status": a.health_status, "tags": a.tags,
        }
        for a in assets
    ]
    return ToolOutput(ok=True, data=data, duration_ms=elapsed)


asset_lookup_tool = Tool(
    name="asset_lookup",
    description="Look up assets by id or fuzzy name match.",
    input_schema={"asset_id": "string (optional)", "name": "string (optional)", "limit": "int (optional)"},
    run=_asset_lookup,
)


# ════════════════════════════════════════════════════════════════════════
#  5. Incident Search Tool
# ════════════════════════════════════════════════════════════════════════

async def _incident_search(input: dict, *, db: Session, **_) -> ToolOutput:
    start = time.monotonic()
    q = db.query(Incident)
    if input.get("asset_id"):
        q = q.filter(Incident.asset_id == input["asset_id"])
    if input.get("severity"):
        q = q.filter(Incident.severity == input["severity"])
    if input.get("status"):
        q = q.filter(Incident.status == input["status"])
    if input.get("text"):
        like = f"%{input['text']}%"
        q = q.filter(or_(Incident.title.ilike(like), Incident.description.ilike(like)))
    incidents = q.order_by(Incident.occurred_at.desc()).limit(int(input.get("limit", 20))).all()
    elapsed = round((time.monotonic() - start) * 1000, 2)
    data = [
        {
            "id": i.id, "title": i.title, "description": i.description,
            "asset_id": i.asset_id, "severity": i.severity.value if i.severity else None,
            "status": i.status.value if i.status else None,
            "failure_mode_code": i.failure_mode_code,
            "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
        }
        for i in incidents
    ]
    return ToolOutput(
        ok=True, data=data,
        source_refs=[{"incident_id": i["id"], "document_title": i["title"]} for i in data],
        duration_ms=elapsed,
    )


incident_search_tool = Tool(
    name="incident_search",
    description="Search historical incidents by asset, severity, status, or free text.",
    input_schema={"asset_id": "string (optional)", "severity": "string (optional)",
                  "status": "string (optional)", "text": "string (optional)", "limit": "int (optional)"},
    run=_incident_search,
)


# ════════════════════════════════════════════════════════════════════════
#  6. Compliance Search Tool — hybrid retrieval scoped to compliance docs
# ════════════════════════════════════════════════════════════════════════

async def _compliance_search(input: dict, *, db: Session, **_) -> ToolOutput:
    query = input.get("query", "")
    filters = RetrievalFilters(document_type="compliance", **{
        k: v for k, v in input.get("filters", {}).items() if k != "document_type"
    })
    try:
        (bm25_chunks, vec_chunks), elapsed = await _timed(
            asyncio.gather(
                retrieval_svc.bm25_retrieve(query=query, top_k=15, filters=filters),
                retrieval_svc.vector_retrieve(query=query, top_k=15, filters=filters),
            )
        )
        fused = retrieval_svc.reciprocal_rank_fusion({"bm25": bm25_chunks, "vector": vec_chunks})
        top = fused[: int(input.get("top_k", 8))]
        return ToolOutput(
            ok=True, data=[c.model_dump(mode="json") for c in top],
            source_refs=[_chunk_to_ref(c) for c in top], duration_ms=elapsed,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("compliance_search_tool_failed: %s", exc)
        return ToolOutput(ok=False, data=[], error=str(exc))


compliance_search_tool = Tool(
    name="compliance_search",
    description="Search compliance / regulatory / procedure documents for a query.",
    input_schema={"query": "string", "top_k": "int (optional)", "filters": "RetrievalFilters (optional)"},
    run=_compliance_search,
)


# ════════════════════════════════════════════════════════════════════════
#  7. Maintenance History Tool — incidents + maintenance docs for an asset
# ════════════════════════════════════════════════════════════════════════

async def _maintenance_history(input: dict, *, db: Session, **_) -> ToolOutput:
    start = time.monotonic()
    asset_id = input.get("asset_id")
    if not asset_id:
        return ToolOutput(ok=False, data=None, error="asset_id is required")

    incidents = (
        db.query(Incident)
        .filter(Incident.asset_id == asset_id)
        .order_by(Incident.occurred_at.desc())
        .limit(int(input.get("limit", 25)))
        .all()
    )
    documents = (
        db.query(Document)
        .filter(Document.asset_id == asset_id)
        .order_by(Document.created_at.desc())
        .limit(int(input.get("limit", 25)))
        .all()
    )
    elapsed = round((time.monotonic() - start) * 1000, 2)
    data = {
        "incidents": [
            {"id": i.id, "title": i.title, "severity": i.severity.value if i.severity else None,
             "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
             "failure_mode_code": i.failure_mode_code}
            for i in incidents
        ],
        "documents": [
            {"id": d.id, "filename": d.original_filename, "category": d.category,
             "created_at": d.created_at.isoformat() if d.created_at else None}
            for d in documents
        ],
    }
    return ToolOutput(ok=True, data=data, duration_ms=elapsed)


maintenance_history_tool = Tool(
    name="maintenance_history",
    description="Retrieve chronological maintenance history (incidents + linked documents) for an asset.",
    input_schema={"asset_id": "string", "limit": "int (optional)"},
    run=_maintenance_history,
)


# ════════════════════════════════════════════════════════════════════════
#  8. RAG Retrieval Tool — full Phase 4 triple-retrieval pipeline
# ════════════════════════════════════════════════════════════════════════

async def _rag_retrieval(input: dict, *, db: Session, **_) -> ToolOutput:
    query = input.get("query", "")
    filters = RetrievalFilters(**input.get("filters", {}))
    try:
        (result, elapsed) = await _timed(
            retrieval_svc.run_triple_retrieval(
                query=query,
                top_k=int(input.get("top_k", 30)),
                top_k_final=int(input.get("top_k_final", 8)),
                filters=filters,
            )
        )
        return ToolOutput(
            ok=True,
            data={
                "chunks": [c.model_dump(mode="json") for c in result.chunks],
                "confidence": result.confidence.model_dump(mode="json") if result.confidence else None,
                "conflicts": [c.model_dump(mode="json") for c in result.conflicts],
                "source_stats": result.source_stats.model_dump(mode="json"),
            },
            source_refs=[_chunk_to_ref(c) for c in result.chunks],
            duration_ms=elapsed,
        )
    except retrieval_svc.RetrievalUnavailableError as exc:
        return ToolOutput(ok=False, data=None, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag_retrieval_tool_failed: %s", exc)
        return ToolOutput(ok=False, data=None, error=str(exc))


rag_retrieval_tool = Tool(
    name="rag_retrieval",
    description="Run the full BM25+vector+graph fused, reranked, confidence-scored retrieval pipeline.",
    input_schema={"query": "string", "top_k": "int (optional)", "top_k_final": "int (optional)",
                  "filters": "RetrievalFilters (optional)"},
    run=_rag_retrieval,
)


# ════════════════════════════════════════════════════════════════════════
#  9. Hybrid Search Tool — BM25 + vector (no graph), lightweight
# ════════════════════════════════════════════════════════════════════════

async def _hybrid_search(input: dict, *, db: Session, **_) -> ToolOutput:
    query = input.get("query", "")
    filters = RetrievalFilters(**input.get("filters", {}))
    try:
        (bm25_chunks, vec_chunks), elapsed = await _timed(
            asyncio.gather(
                retrieval_svc.bm25_retrieve(query=query, top_k=int(input.get("top_k", 15)), filters=filters),
                retrieval_svc.vector_retrieve(query=query, top_k=int(input.get("top_k", 15)), filters=filters),
            )
        )
        fused = retrieval_svc.reciprocal_rank_fusion({"bm25": bm25_chunks, "vector": vec_chunks})
        top = fused[: int(input.get("top_k_final", 8))]
        return ToolOutput(
            ok=True, data=[c.model_dump(mode="json") for c in top],
            source_refs=[_chunk_to_ref(c) for c in top], duration_ms=elapsed,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("hybrid_search_tool_failed: %s", exc)
        return ToolOutput(ok=False, data=[], error=str(exc))


hybrid_search_tool = Tool(
    name="hybrid_search",
    description="BM25 + vector fused search (no graph expansion) — faster than full rag_retrieval.",
    input_schema={"query": "string", "top_k": "int (optional)", "top_k_final": "int (optional)"},
    run=_hybrid_search,
)


# ════════════════════════════════════════════════════════════════════════
#  10. Prompt Library Tool
# ════════════════════════════════════════════════════════════════════════

async def _prompt_library(input: dict, *, db: Session, **_) -> ToolOutput:
    import os
    start = time.monotonic()
    name = input.get("name", "")
    safe_name = os.path.basename(name)  # prevent path traversal
    path = os.path.join(os.path.dirname(__file__), "..", "prompts", "agents", f"{safe_name}.md")
    path = os.path.normpath(path)
    elapsed = round((time.monotonic() - start) * 1000, 2)
    if not os.path.isfile(path):
        return ToolOutput(ok=False, data=None, error=f"Prompt template '{safe_name}' not found", duration_ms=elapsed)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return ToolOutput(ok=True, data={"name": safe_name, "content": content}, duration_ms=elapsed)


prompt_library_tool = Tool(
    name="prompt_library",
    description="Fetch a versioned agent prompt template by name (rca, maintenance, compliance, lessons).",
    input_schema={"name": "string"},
    run=_prompt_library,
)


# ════════════════════════════════════════════════════════════════════════
#  11. Conversation History Tool
# ════════════════════════════════════════════════════════════════════════

async def _conversation_history(input: dict, *, db: Session, **_) -> ToolOutput:
    start = time.monotonic()
    session_id = input.get("session_id")
    user_id = input.get("user_id")
    data: dict[str, Any] = {"messages": [], "queries": []}
    if session_id:
        session = db.query(ConversationSession).filter(ConversationSession.id == session_id).first()
        if session:
            data["messages"] = session.recent_messages
    if user_id:
        queries = (
            db.query(QueryHistory)
            .filter(QueryHistory.user_id == user_id)
            .order_by(QueryHistory.created_at.desc())
            .limit(int(input.get("limit", 10)))
            .all()
        )
        data["queries"] = [
            {"id": q.id, "query": q.query_text, "response": q.response_text,
             "created_at": q.created_at.isoformat() if q.created_at else None}
            for q in queries
        ]
    elapsed = round((time.monotonic() - start) * 1000, 2)
    return ToolOutput(ok=True, data=data, duration_ms=elapsed)


conversation_history_tool = Tool(
    name="conversation_history",
    description="Fetch prior conversation messages and/or recent query history for a session or user.",
    input_schema={"session_id": "string (optional)", "user_id": "string (optional)", "limit": "int (optional)"},
    run=_conversation_history,
)


# ════════════════════════════════════════════════════════════════════════
#  12. Audit Lookup Tool (RESTRICTED — sensitive)
# ════════════════════════════════════════════════════════════════════════

async def _audit_lookup(input: dict, *, db: Session, **_) -> ToolOutput:
    start = time.monotonic()
    q = db.query(AuditLog)
    if input.get("resource"):
        q = q.filter(AuditLog.resource.ilike(f"%{input['resource']}%"))
    if input.get("user_id"):
        q = q.filter(AuditLog.user_id == input["user_id"])
    if input.get("action"):
        q = q.filter(AuditLog.action == input["action"])
    logs = q.order_by(AuditLog.timestamp.desc()).limit(int(input.get("limit", 20))).all()
    elapsed = round((time.monotonic() - start) * 1000, 2)
    data = [
        {"id": l.id, "action": l.action.value if l.action else None, "status": l.status.value if l.status else None,
         "resource": l.resource, "user_id": l.user_id, "timestamp": l.timestamp.isoformat() if l.timestamp else None}
        for l in logs
    ]
    return ToolOutput(ok=True, data=data, duration_ms=elapsed)


audit_lookup_tool = Tool(
    name="audit_lookup",
    description="Look up audit log entries by resource, user, or action. Restricted to admin/engineer roles.",
    input_schema={"resource": "string (optional)", "user_id": "string (optional)",
                  "action": "string (optional)", "limit": "int (optional)"},
    run=_audit_lookup,
    sensitive=True,
)


# ════════════════════════════════════════════════════════════════════════
#  Registry
# ════════════════════════════════════════════════════════════════════════

ALL_TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        semantic_search_tool,
        knowledge_graph_tool,
        document_reader_tool,
        asset_lookup_tool,
        incident_search_tool,
        compliance_search_tool,
        maintenance_history_tool,
        rag_retrieval_tool,
        hybrid_search_tool,
        prompt_library_tool,
        conversation_history_tool,
        audit_lookup_tool,
    ]
}


def get_tool(name: str) -> Optional[Tool]:
    return ALL_TOOLS.get(name)


def list_tools(include_sensitive: bool = True) -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema, "sensitive": t.sensitive}
        for t in ALL_TOOLS.values()
        if include_sensitive or not t.sensitive
    ]


async def execute_tool(name: str, input: dict, *, db: Session, current_user: Optional[User] = None) -> ToolOutput:
    """
    Validates permission on sensitive tools, then executes.
    Never raises — tool failures are captured in ToolOutput.error so
    LangGraph nodes can branch on `ok` without try/except at every call site.
    """
    tool = get_tool(name)
    if tool is None:
        return ToolOutput(ok=False, data=None, error=f"Unknown tool '{name}'")

    if tool.sensitive and current_user is not None:
        role = getattr(current_user, "role", None)
        role_value = getattr(role, "value", role)
        if role_value not in ("admin", "engineer"):
            return ToolOutput(ok=False, data=None, error="Insufficient permissions for sensitive tool")

    try:
        return await tool.run(input, db=db, current_user=current_user)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool_execution_failed name=%s", name)
        return ToolOutput(ok=False, data=None, error=str(exc))
