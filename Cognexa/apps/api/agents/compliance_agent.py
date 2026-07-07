"""
apps/api/agents/compliance_agent.py

Phase 5 — Agent 3: Compliance Agent.

Responsibilities (per spec): search compliance documents, validate
procedures, check missing documentation, identify policy violations,
generate a compliance report, recommend corrective actions, generate
an audit summary.

Note: audit_lookup is a SENSITIVE tool (see agents/tools.py) — access is
restricted to admin/engineer roles by execute_tool()'s permission check,
enforced regardless of what the planner proposes.
"""
from __future__ import annotations

from apps.api.agents.base_agent import BaseAgent
from apps.api.agents.state import AgentState


class ComplianceAgent(BaseAgent):
    agent_id = "compliance_agent"
    name = "Compliance Agent"
    description = (
        "Validates assets, processes, and documentation against compliance "
        "and regulatory requirements, flags violations, and produces audit-ready "
        "summaries."
    )
    version = "1.0.0"
    prompt_file = "compliance"
    max_retries = 2
    capabilities = [
        "compliance_search",
        "document_reader",
        "asset_lookup",
        "audit_lookup",
        "knowledge_graph_query",
        "hybrid_search",
        "rag_retrieval",
    ]

    def build_structured_output(self, state: AgentState) -> dict:
        tool_results = state.get("tool_results", [])
        audit_entries = next(
            (t["output"] for t in tool_results if t["tool_name"] == "audit_lookup" and t.get("ok")), []
        )
        compliance_docs = [d for d in state.get("retrieved_documents", []) if isinstance(d, dict)]
        return {
            "task_type": "compliance_review",
            "compliance_documents_reviewed": len(compliance_docs),
            "audit_entries": audit_entries,
            "evidence_counts": {
                "documents": len(state.get("retrieved_documents", [])),
                "graph_results": len(state.get("graph_results", [])),
                "tool_results": len(tool_results),
            },
        }


compliance_agent = ComplianceAgent()
