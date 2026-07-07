"""
apps/api/tests/agents/test_streaming.py

Streaming tests: verifies agent.stream() yields one event per LangGraph
node in the correct order and that internal (non-serializable) state
like the DB session is never leaked into a streamed event.
"""
from __future__ import annotations

import pytest

from apps.api.agents.rca_agent import rca_agent


@pytest.mark.asyncio
class TestAgentStreaming:
    async def test_stream_yields_one_event_per_node_in_order(
        self, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        node_order = []
        async for event in rca_agent.stream("exec-stream-1", "Investigate a failure", fake_db):
            node_order.append(event["node"])

        assert node_order[0] == "planner"
        assert node_order[-1] == "response_generator"
        assert "reasoner" in node_order
        assert "validator" in node_order

    async def test_stream_events_never_contain_db_session(
        self, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        async for event in rca_agent.stream("exec-stream-2", "Investigate a failure", fake_db):
            output = event["output"]
            context = output.get("context")
            if isinstance(context, dict):
                assert "_db" not in context

    async def test_stream_final_event_has_answer_and_confidence(
        self, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        last_output = None
        async for event in rca_agent.stream("exec-stream-3", "Investigate a failure", fake_db):
            last_output = event["output"]
        assert last_output.get("answer")
        assert last_output.get("confidence")

    async def test_active_db_registry_cleaned_up_after_stream(
        self, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        execution_id = "exec-stream-cleanup"
        async for _ in rca_agent.stream(execution_id, "goal", fake_db):
            pass
        assert execution_id not in rca_agent._active_dbs
