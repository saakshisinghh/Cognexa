"""
apps/api/tests/agents/test_integration_workflow.py

Integration tests for services/workflow_engine.py — exercises the real
SQLAlchemy ORM models (AgentWorkflow, AgentExecution, AgentExecutionStep,
AgentDefinition) against an in-memory SQLite database, with only the LLM
gateway and tool dispatcher mocked (matching the other agent tests).
This is a genuine end-to-end integration test of persistence + multi-agent
orchestration, as distinct from the pure-unit tests elsewhere in this suite.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.db import Base
from apps.api.services import agent_registry, workflow_engine, agent_executor
from apps.api.models.agent import AgentExecutionStatus


@pytest.fixture
def sqlite_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # Only create the tables Phase 5 workflows actually touch. The full
    # Base.metadata includes Postgres-only column types (e.g. JSONB) from
    # earlier phases' models that SQLite's DDL compiler can't render —
    # irrelevant to what's under test here, so we scope create_all() to
    # just the required tables rather than pulling in the whole schema.
    required_tables = [
        Base.metadata.tables[name] for name in (
            "users", "audit_logs", "agent_definitions", "agent_workflows",
            "agent_executions", "agent_execution_steps",
        )
    ]
    Base.metadata.create_all(bind=engine, tables=required_tables)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    agent_registry.sync_agent_definitions(session)
    yield session
    session.close()


@pytest.fixture
def workflow_llm_and_tools(monkeypatch):
    """Mocks the LLM (planner + reasoner + supervisor + conflict-detector
    prompts) and the tool dispatcher, matching conftest's per-agent fixtures
    but shared here across every agent invoked by a workflow."""
    async def fake_complete(messages, **kwargs):
        system = messages[0]["content"] if messages else ""
        user = messages[-1]["content"] if messages else ""
        if "Respond with EXACTLY this JSON shape" in system:
            return json.dumps({
                "goal_summary": "test", "task_type": "test",
                "tasks": [{"task": "search", "tool": "incident_search", "tool_input": {}}],
                "estimated_confidence": 0.6,
            }), 10, 10
        if '"order"' in user or "supervisor coordinating" in user:
            return json.dumps({"order": []}), 10, 10  # empty -> engine falls back to given order
        if '"conflicts"' in user or "contradiction" in user.lower():
            return json.dumps({"conflicts": []}), 10, 10
        return "Synthesized finding for the goal.", 10, 10

    async def fake_execute_tool(name, input, db=None, current_user=None):
        from apps.api.agents.tools import ToolOutput
        return ToolOutput(ok=True, data=[{"id": "inc-1", "failure_mode_code": "X"}], source_refs=[])

    import apps.api.agents.planner as planner_mod
    import apps.api.agents.base_agent as base_agent_mod
    import apps.api.services.workflow_engine as workflow_mod

    monkeypatch.setattr(planner_mod, "complete_response", fake_complete)
    monkeypatch.setattr(base_agent_mod, "complete_response", fake_complete)
    monkeypatch.setattr(base_agent_mod, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(workflow_mod, "complete_response", fake_complete)


@pytest.mark.asyncio
class TestSequentialWorkflow:
    async def test_sequential_workflow_runs_all_agents_and_completes(self, sqlite_db, workflow_llm_and_tools):
        workflow = await workflow_engine.run_workflow(
            sqlite_db, goal="Investigate and plan maintenance for pump P-1045",
            agent_keys=["rca_agent", "maintenance_agent"], mode="sequential",
        )
        assert workflow.status == AgentExecutionStatus.completed
        executions = workflow_engine.get_workflow_executions(sqlite_db, workflow.id)
        assert len(executions) == 2
        assert all(e.status == AgentExecutionStatus.completed for e in executions)

    async def test_sequential_workflow_hands_off_prior_findings(self, sqlite_db, workflow_llm_and_tools):
        workflow = await workflow_engine.run_workflow(
            sqlite_db, goal="goal", agent_keys=["rca_agent", "maintenance_agent"], mode="sequential",
        )
        # shared_context should have accumulated a confidence entry from the first agent
        assert "rca_agent_confidence" in (workflow.shared_context or {})

    async def test_workflow_final_answer_synthesized_from_completed_agents(self, sqlite_db, workflow_llm_and_tools):
        workflow = await workflow_engine.run_workflow(
            sqlite_db, goal="goal", agent_keys=["rca_agent", "compliance_agent"], mode="sequential",
        )
        assert workflow.final_answer


@pytest.mark.asyncio
class TestParallelWorkflow:
    async def test_parallel_workflow_runs_agents_concurrently(self, sqlite_db, workflow_llm_and_tools):
        workflow = await workflow_engine.run_workflow(
            sqlite_db, goal="goal", agent_keys=["rca_agent", "lessons_agent"], mode="parallel",
        )
        assert workflow.status == AgentExecutionStatus.completed
        executions = workflow_engine.get_workflow_executions(sqlite_db, workflow.id)
        assert len(executions) == 2


@pytest.mark.asyncio
class TestSupervisorWorkflow:
    async def test_supervisor_falls_back_to_given_order_on_empty_plan(self, sqlite_db, workflow_llm_and_tools):
        workflow = await workflow_engine.run_workflow(
            sqlite_db, goal="goal", agent_keys=["rca_agent", "maintenance_agent"], mode="supervisor",
        )
        assert workflow.status == AgentExecutionStatus.completed
        assert set(workflow.agent_keys) == {"rca_agent", "maintenance_agent"}


@pytest.mark.asyncio
class TestWorkflowValidation:
    async def test_invalid_agent_keys_raises(self, sqlite_db, workflow_llm_and_tools):
        with pytest.raises(agent_executor.AgentNotFoundError):
            await workflow_engine.run_workflow(
                sqlite_db, goal="goal", agent_keys=["not_a_real_agent"], mode="sequential",
            )

    async def test_disabled_agent_excluded_from_workflow(self, sqlite_db, workflow_llm_and_tools):
        agent_registry.set_enabled(sqlite_db, "compliance_agent", False)
        workflow = await workflow_engine.run_workflow(
            sqlite_db, goal="goal", agent_keys=["rca_agent", "compliance_agent"], mode="sequential",
        )
        assert "compliance_agent" not in workflow.agent_keys
        assert "rca_agent" in workflow.agent_keys
