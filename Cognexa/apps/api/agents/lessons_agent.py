"""
apps/api/agents/lessons_agent.py

Phase 5 — Agent 4: Lessons Learned Agent.

Responsibilities (per spec): search historical incidents, find recurring
patterns, cluster similar failures, extract best practices, generate
recommendations, create reusable knowledge, generate an executive summary.
"""
from __future__ import annotations

from collections import Counter

from apps.api.agents.base_agent import BaseAgent
from apps.api.agents.state import AgentState


class LessonsLearnedAgent(BaseAgent):
    agent_id = "lessons_agent"
    name = "Lessons Learned Agent"
    description = (
        "Mines historical incidents for recurring failure patterns and converts "
        "them into reusable organizational knowledge and executive summaries."
    )
    version = "1.0.0"
    prompt_file = "lessons"
    max_retries = 2
    capabilities = [
        "incident_search",
        "knowledge_graph_query",
        "semantic_search",
        "hybrid_search",
        "rag_retrieval",
        "document_reader",
        "conversation_history",
    ]

    def build_structured_output(self, state: AgentState) -> dict:
        tool_results = state.get("tool_results", [])
        incidents = next(
            (t["output"] for t in tool_results if t["tool_name"] == "incident_search" and t.get("ok")), []
        )
        failure_modes = Counter(
            i.get("failure_mode_code") for i in (incidents or []) if isinstance(i, dict) and i.get("failure_mode_code")
        )
        recurring = [{"failure_mode_code": code, "count": count} for code, count in failure_modes.items() if count >= 2]
        return {
            "task_type": "lessons_learned",
            "incidents_analyzed": len(incidents or []),
            "recurring_patterns": recurring,
            "evidence_counts": {
                "documents": len(state.get("retrieved_documents", [])),
                "graph_results": len(state.get("graph_results", [])),
                "tool_results": len(tool_results),
            },
        }


lessons_agent = LessonsLearnedAgent()
