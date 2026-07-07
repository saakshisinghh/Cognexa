"""
apps/api/tests/agents/test_langgraph_agents.py

LangGraph / Agent tests: verifies each of the four concrete agents
compiles a valid StateGraph, executes the full node sequence in order,
respects the retry loop, and produces the expected structured output
shape. Uses patch_llm_planner_and_reasoner + patch_tool_execution from
conftest.py so no live LLM/DB/retrieval backend is required.
"""
from __future__ import annotations

import pytest

from apps.api.agents.rca_agent import rca_agent
from apps.api.agents.maintenance_agent import maintenance_agent
from apps.api.agents.compliance_agent import compliance_agent
from apps.api.agents.lessons_agent import lessons_agent

ALL_AGENTS = [rca_agent, maintenance_agent, compliance_agent, lessons_agent]


class TestGraphCompilation:
    @pytest.mark.parametrize("agent", ALL_AGENTS, ids=lambda a: a.agent_id)
    def test_graph_compiles(self, agent):
        assert agent._graph is not None

    @pytest.mark.parametrize("agent", ALL_AGENTS, ids=lambda a: a.agent_id)
    def test_agent_has_required_identity_fields(self, agent):
        assert agent.agent_id
        assert agent.name
        assert agent.description
        assert agent.version
        assert agent.capabilities


@pytest.mark.asyncio
class TestAgentExecution:
    @pytest.mark.parametrize("agent", ALL_AGENTS, ids=lambda a: a.agent_id)
    async def test_full_run_completes_with_expected_node_sequence(
        self, agent, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        state = await agent.run(f"exec-{agent.agent_id}", "Investigate a test failure", fake_db, user_id="u1")

        assert state["completion_status"] == "completed"
        assert state["answer"]
        assert state["confidence"]

        step_names = [h["step"] for h in state["execution_history"]]
        assert step_names[0] == "planner"
        assert step_names[-1] == "response_generator"
        assert "reasoner" in step_names
        assert "validator" in step_names

    @pytest.mark.parametrize("agent", ALL_AGENTS, ids=lambda a: a.agent_id)
    async def test_structured_output_matches_agent_task_type(
        self, agent, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        state = await agent.run(f"exec-struct-{agent.agent_id}", "goal", fake_db)
        structured = state["structured_output"]
        assert "task_type" in structured

    async def test_rca_structured_output_includes_similar_incidents(
        self, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        state = await rca_agent.run("exec-rca-1", "Why did the pump fail?", fake_db)
        assert state["structured_output"]["task_type"] == "root_cause_analysis"
        assert isinstance(state["structured_output"]["similar_incidents"], list)

    async def test_lessons_agent_requires_two_instances_for_recurring_pattern(
        self, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        # conftest's fake incident_search returns 2 incidents sharing
        # failure_mode_code "BRG-01" — this should surface as a recurring pattern.
        state = await lessons_agent.run("exec-lessons-1", "Find recurring failure patterns", fake_db)
        patterns = state["structured_output"]["recurring_patterns"]
        assert any(p["failure_mode_code"] == "BRG-01" and p["count"] >= 2 for p in patterns)


@pytest.mark.asyncio
class TestRetryLoop:
    async def test_validator_triggers_retry_when_no_evidence_gathered(self, fake_db, monkeypatch):
        """
        If the plan yields zero tool/retrieval/graph results, the Validator
        should route back to the Retriever (up to max_retries) rather than
        immediately producing a low-effort answer.
        """
        import apps.api.agents.planner as planner_mod
        import apps.api.agents.base_agent as base_agent_mod
        from apps.api.agents.tools import ToolOutput
        import json

        async def empty_plan(messages, **kwargs):
            if "Respond with EXACTLY this JSON shape" in messages[0]["content"]:
                return json.dumps({
                    "goal_summary": "x", "task_type": "t",
                    "tasks": [{"task": "noop", "tool": None, "tool_input": {}}],
                    "estimated_confidence": 0.1,
                }), 10, 10
            return "No evidence was found to support a conclusion.", 10, 10

        async def no_op_tool(name, input, db=None, current_user=None):
            return ToolOutput(ok=True, data=[], source_refs=[])

        monkeypatch.setattr(planner_mod, "complete_response", empty_plan)
        monkeypatch.setattr(base_agent_mod, "complete_response", empty_plan)
        monkeypatch.setattr(base_agent_mod, "execute_tool", no_op_tool)

        state = await rca_agent.run("exec-retry-1", "goal with no evidence", fake_db)

        step_names = [h["step"] for h in state["execution_history"]]
        validator_hits = step_names.count("validator")
        # max_retries=2 on RCAAgent => validator should run at least twice
        # (initial pass + at least one retry) before finalizing.
        assert validator_hits >= 2
        assert state["completion_status"] == "completed"  # eventually finalizes rather than looping forever
