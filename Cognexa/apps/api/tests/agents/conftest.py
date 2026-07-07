"""
apps/api/tests/agents/conftest.py

Shared fixtures for the Phase 5 agent test suite.

Design: rather than standing up Postgres/Weaviate/Neo4j/Redis/Ollama for
every test, these fixtures patch the two seams every agent graph goes
through — the LLM gateway (services.llm_gateway.complete_response) and
the tool dispatcher (agents.tools.execute_tool) — with deterministic
fakes. This tests the actual LangGraph wiring, planning, retries,
confidence handling, and node sequencing logic (the Phase 5 deliverable)
without depending on external services (the Phase 1-4 deliverables,
already covered by their own test suites).
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from apps.api.agents.tools import ToolOutput


class FakeDB:
    """Stand-in for a SQLAlchemy Session — agent nodes never call DB
    methods directly (all DB access goes through tools.execute_tool,
    which is patched in these tests), so this only needs to exist."""
    pass


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def patch_llm_planner_and_reasoner(monkeypatch):
    """
    Patches complete_response everywhere it's imported (planner.py,
    base_agent.py) with a fake that returns a valid plan for the
    planner's structured-JSON prompt, and a plain sentence for any
    other (reasoning / synthesis) call.
    """
    async def fake_complete(messages, **kwargs):
        system_content = messages[0]["content"] if messages else ""
        if "Respond with EXACTLY this JSON shape" in system_content:
            plan = {
                "goal_summary": "Test goal summary",
                "task_type": "test_task",
                "tasks": [
                    {"task": "search incidents", "tool": "incident_search",
                     "tool_input": {"asset_id": "A1"}, "rationale": "history check"},
                    {"task": "run rag retrieval", "tool": "rag_retrieval",
                     "tool_input": {"query": "test query"}, "rationale": "grounding"},
                ],
                "estimated_confidence": 0.7,
            }
            return json.dumps(plan), 120, 60
        return "This is a synthesized test answer citing the gathered evidence.", 200, 80

    import apps.api.agents.planner as planner_mod
    import apps.api.agents.base_agent as base_agent_mod

    monkeypatch.setattr(planner_mod, "complete_response", fake_complete)
    monkeypatch.setattr(base_agent_mod, "complete_response", fake_complete)
    return fake_complete


@pytest.fixture
def patch_tool_execution(monkeypatch):
    """Patches agents.base_agent.execute_tool with deterministic fakes
    per tool name, so retriever/graph_query/tool_executor nodes have
    something to accumulate without touching real infrastructure."""
    async def fake_execute_tool(name: str, input: dict, db: Any = None, current_user: Any = None) -> ToolOutput:
        if name == "incident_search":
            return ToolOutput(ok=True, data=[
                {"id": "inc-1", "title": "Bearing failure", "failure_mode_code": "BRG-01"},
                {"id": "inc-2", "title": "Bearing failure repeat", "failure_mode_code": "BRG-01"},
            ], source_refs=[{"incident_id": "inc-1"}])
        if name == "rag_retrieval":
            return ToolOutput(ok=True, data={
                "chunks": [], "confidence": None, "conflicts": [], "source_stats": {},
            }, source_refs=[])
        if name == "knowledge_graph_query":
            return ToolOutput(ok=True, data={"nodes": [], "edges": []})
        if name == "audit_lookup":
            return ToolOutput(ok=False, data=None, error="Insufficient permissions for sensitive tool")
        return ToolOutput(ok=True, data=[], source_refs=[])

    import apps.api.agents.base_agent as base_agent_mod
    monkeypatch.setattr(base_agent_mod, "execute_tool", fake_execute_tool)
    return fake_execute_tool
