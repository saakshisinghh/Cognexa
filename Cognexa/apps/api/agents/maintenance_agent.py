"""
apps/api/agents/maintenance_agent.py

Phase 5 — Agent 2: Predictive Maintenance Agent.

Responsibilities (per spec): analyze equipment, read manuals, inspect
previous failures, generate maintenance plans, recommend inspection
schedules, identify critical assets, estimate downtime/risk, suggest
spare parts, recommend maintenance windows.
"""
from __future__ import annotations

from apps.api.agents.base_agent import BaseAgent
from apps.api.agents.state import AgentState


class MaintenanceAgent(BaseAgent):
    agent_id = "maintenance_agent"
    name = "Predictive Maintenance Agent"
    description = (
        "Builds maintenance plans, inspection schedules, and risk/downtime "
        "estimates for industrial assets from manuals, failure history, and "
        "the knowledge graph."
    )
    version = "1.0.0"
    prompt_file = "maintenance"
    max_retries = 2
    capabilities = [
        "asset_lookup",
        "maintenance_history",
        "incident_search",
        "document_reader",
        "knowledge_graph_query",
        "semantic_search",
        "hybrid_search",
        "rag_retrieval",
    ]

    def build_structured_output(self, state: AgentState) -> dict:
        tool_results = state.get("tool_results", [])
        asset_info = next(
            (t["output"] for t in tool_results if t["tool_name"] == "asset_lookup" and t.get("ok")), []
        )
        maintenance_history = next(
            (t["output"] for t in tool_results if t["tool_name"] == "maintenance_history" and t.get("ok")), None
        )
        return {
            "task_type": "predictive_maintenance",
            "asset_info": asset_info,
            "maintenance_history": maintenance_history,
            "similar_asset_relationships": len(state.get("graph_results", [])),
            "evidence_counts": {
                "documents": len(state.get("retrieved_documents", [])),
                "graph_results": len(state.get("graph_results", [])),
                "tool_results": len(tool_results),
            },
        }


maintenance_agent = MaintenanceAgent()
