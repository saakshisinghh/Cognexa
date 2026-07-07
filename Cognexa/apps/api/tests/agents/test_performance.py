"""
apps/api/tests/agents/test_performance.py

Performance tests — with the LLM and tool backends mocked (as in the
rest of this suite), these assert on ORCHESTRATION overhead only: that
the LangGraph node-sequencing/state-merging machinery itself stays
fast and that parallel workflow execution is actually concurrent
(wall-clock time close to the slowest single agent, not the sum of all
agents). This does NOT benchmark real LLM/retrieval latency — that is
an infrastructure characteristic, not something Phase 5's own code
controls, and is out of scope for a unit-style suite.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from apps.api.agents.rca_agent import rca_agent
from apps.api.services import workflow_engine


@pytest.mark.asyncio
class TestOrchestrationOverhead:
    async def test_single_agent_run_orchestration_overhead_is_small(
        self, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        start = time.monotonic()
        await rca_agent.run("perf-exec-1", "Investigate a failure", fake_db)
        elapsed = time.monotonic() - start
        # With LLM/tool calls mocked to be near-instant, all remaining time
        # is LangGraph + our node bookkeeping overhead — should be well
        # under a second.
        assert elapsed < 2.0

    async def test_repeated_runs_do_not_leak_active_db_entries(
        self, fake_db, patch_llm_planner_and_reasoner, patch_tool_execution,
    ):
        for i in range(5):
            await rca_agent.run(f"perf-exec-leak-{i}", "goal", fake_db)
        assert len(rca_agent._active_dbs) == 0


@pytest.mark.asyncio
class TestParallelWorkflowConcurrency:
    async def test_parallel_workflow_is_actually_concurrent(self, monkeypatch):
        """
        Patches agent_executor.execute_agent with a fake that sleeps 0.2s,
        then asserts a 2-agent parallel workflow takes closer to 0.2s than
        0.4s — proving _run_parallel uses asyncio.gather rather than
        awaiting agents one at a time.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from apps.api.db import Base
        from apps.api.services import agent_registry

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        tables = [Base.metadata.tables[n] for n in (
            "users", "audit_logs", "agent_definitions", "agent_workflows",
            "agent_executions", "agent_execution_steps",
        )]
        Base.metadata.create_all(bind=engine, tables=tables)
        db = sessionmaker(bind=engine)()
        agent_registry.sync_agent_definitions(db)

        async def slow_execute_agent(db, *, agent_key, goal, context=None, current_user=None,
                                       workflow_id=None, execution=None):
            await asyncio.sleep(0.2)
            from apps.api.models.agent import AgentExecution, AgentExecutionStatus
            execution = AgentExecution(
                agent_key=agent_key, goal=goal, status=AgentExecutionStatus.completed,
                workflow_id=workflow_id, answer="done", confidence={"level": "high"},
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)
            return execution

        import apps.api.services.workflow_engine as workflow_mod
        monkeypatch.setattr(workflow_mod.agent_executor, "execute_agent", slow_execute_agent)

        async def fake_conflicts(executions):
            return []
        monkeypatch.setattr(workflow_mod, "_detect_conflicts", fake_conflicts)

        async def fake_synthesize(workflow, executions):
            return "done"
        monkeypatch.setattr(workflow_mod, "_synthesize_final_answer", fake_synthesize)

        start = time.monotonic()
        await workflow_engine.run_workflow(
            db, goal="goal", agent_keys=["rca_agent", "maintenance_agent"], mode="parallel",
        )
        elapsed = time.monotonic() - start

        assert elapsed < 0.35  # concurrent: ~0.2s, NOT sequential ~0.4s
