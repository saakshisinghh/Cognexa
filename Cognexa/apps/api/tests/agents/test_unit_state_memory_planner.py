"""
apps/api/tests/agents/test_unit_state_memory_planner.py

Unit tests: AgentState reducers, ExecutionMemory (Redis-backed with
local fallback), and the Planner's JSON extraction / fallback behavior.
"""
from __future__ import annotations

import json

import pytest

from apps.api.agents.state import _merge_dicts
from apps.api.agents.memory import ExecutionMemory
from apps.api.agents.planner import _extract_json, generate_plan, _FALLBACK_PLAN


class TestStateReducers:
    def test_merge_dicts_right_wins(self):
        left = {"a": 1, "b": 2}
        right = {"b": 3, "c": 4}
        assert _merge_dicts(left, right) == {"a": 1, "b": 3, "c": 4}

    def test_merge_dicts_handles_none(self):
        assert _merge_dicts(None, {"a": 1}) == {"a": 1}
        assert _merge_dicts({"a": 1}, None) == {"a": 1}


class TestExecutionMemory:
    def test_local_fallback_when_redis_unavailable(self, monkeypatch):
        import apps.api.agents.memory as memory_mod

        def broken_redis():
            raise ConnectionError("redis down")

        monkeypatch.setattr(memory_mod, "get_redis", broken_redis)
        mem = ExecutionMemory("exec-1")
        mem.set_goal("investigate pump failure")
        assert mem.get_goal() == "investigate pump failure"

    def test_conversation_round_trip_local_fallback(self, monkeypatch):
        import apps.api.agents.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_redis", lambda: (_ for _ in ()).throw(ConnectionError()))

        mem = ExecutionMemory("exec-2")
        mem.append_message("user", "why did it fail?")
        mem.append_message("assistant", "likely bearing wear")
        convo = mem.get_conversation()
        assert convo == [
            {"role": "user", "content": "why did it fail?"},
            {"role": "assistant", "content": "likely bearing wear"},
        ]

    def test_clear_removes_all_fields(self, monkeypatch):
        import apps.api.agents.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_redis", lambda: (_ for _ in ()).throw(ConnectionError()))

        mem = ExecutionMemory("exec-3")
        mem.set_goal("goal")
        mem.append_message("user", "hi")
        mem.clear()
        assert mem.get_goal() is None
        assert mem.get_conversation() == []


class TestPlannerJSONExtraction:
    def test_extracts_plain_json(self):
        raw = '{"goal_summary": "x", "tasks": []}'
        assert _extract_json(raw) == {"goal_summary": "x", "tasks": []}

    def test_extracts_json_from_markdown_fence(self):
        raw = '```json\n{"goal_summary": "x", "tasks": []}\n```'
        assert _extract_json(raw) == {"goal_summary": "x", "tasks": []}

    def test_extracts_json_with_preamble_text(self):
        raw = 'Sure, here is the plan:\n{"goal_summary": "x", "tasks": []}\nHope that helps!'
        assert _extract_json(raw) == {"goal_summary": "x", "tasks": []}

    def test_raises_on_unparseable_text(self):
        with pytest.raises(ValueError):
            _extract_json("This is not JSON at all.")

    @pytest.mark.asyncio
    async def test_generate_plan_falls_back_on_llm_unavailable(self, monkeypatch):
        import apps.api.agents.planner as planner_mod
        from apps.api.services.llm_gateway import LLMUnavailableError

        async def broken_complete(messages, **kwargs):
            raise LLMUnavailableError("backend down")

        monkeypatch.setattr(planner_mod, "complete_response", broken_complete)

        plan = await generate_plan("Why did the pump fail?", "RCA Agent", [
            {"name": "rag_retrieval", "description": "d", "input_schema": {}},
        ])
        assert plan.tasks  # fallback plan always has at least one task
        assert plan.tasks[0].tool == _FALLBACK_PLAN["tasks"][0]["tool"]

    @pytest.mark.asyncio
    async def test_generate_plan_drops_unknown_tool_names(self, monkeypatch):
        import apps.api.agents.planner as planner_mod

        async def fake_complete(messages, **kwargs):
            return json.dumps({
                "goal_summary": "x", "task_type": "t",
                "tasks": [{"task": "do a thing", "tool": "nonexistent_tool", "tool_input": {}}],
                "estimated_confidence": 0.5,
            }), 10, 10

        monkeypatch.setattr(planner_mod, "complete_response", fake_complete)
        plan = await generate_plan("goal", "Agent", [{"name": "rag_retrieval", "description": "d", "input_schema": {}}])
        assert plan.tasks[0].tool is None  # unknown tool name was stripped
