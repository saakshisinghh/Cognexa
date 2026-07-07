"""
apps/api/agents/rca_agent.py

Phase 5 — Agent 1: Root Cause Analysis Agent.

Responsibilities (per spec): analyze incidents, retrieve similar failures,
query Neo4j, search documents, analyze maintenance history, generate and
rank probable root causes, suggest investigations, recommend preventive
actions, generate a confidence score.

All retrieval/graph/tool logic is inherited from BaseAgent — this class
only declares the agent's identity, tool capabilities, and how to shape
its structured output for the frontend (ranked causes list rather than
the generic evidence-count summary BaseAgent provides by default).
"""
from __future__ import annotations

from apps.api.agents.base_agent import BaseAgent
from apps.api.agents.state import AgentState


class RCAAgent(BaseAgent):
    agent_id = "rca_agent"
    name = "Root Cause Analysis Agent"
    description = (
        "Analyzes industrial incidents and equipment failures to identify, rank, "
        "and explain probable root causes using historical incidents, the "
        "knowledge graph, and enterprise documents."
    )
    version = "1.0.0"
    prompt_file = "rca"
    max_retries = 2
    capabilities = [
        "incident_search",
        "knowledge_graph_query",
        "semantic_search",
        "hybrid_search",
        "rag_retrieval",
        "maintenance_history",
        "asset_lookup",
        "document_reader",
    ]

    def build_structured_output(self, state: AgentState) -> dict:
        tool_results = state.get("tool_results", [])
        incident_matches = next(
            (t["output"] for t in tool_results if t["tool_name"] == "incident_search" and t.get("ok")), []
        )
        maintenance = next(
            (t["output"] for t in tool_results if t["tool_name"] == "maintenance_history" and t.get("ok")), None
        )
        return {
            "task_type": "root_cause_analysis",
            "similar_incidents": incident_matches,
            "maintenance_context": maintenance,
            "graph_relationships_found": len(state.get("graph_results", [])),
            "evidence_counts": {
                "documents": len(state.get("retrieved_documents", [])),
                "graph_results": len(state.get("graph_results", [])),
                "tool_results": len(tool_results),
            },
        }


rca_agent = RCAAgent()
