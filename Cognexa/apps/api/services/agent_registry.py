"""
apps/api/services/agent_registry.py

Phase 5 — Agent Registry.

Registers all agents dynamically at process startup (from apps.api.agents),
persists their descriptor rows in AgentDefinition (created once, then
kept in sync), and exposes:

    - list_agents()      — capability discovery for the frontend Agent Catalog
    - get_agent()         — resolve agent_key -> BaseAgent instance (only if enabled)
    - set_enabled()       — enable/disable an agent (admin action, audited by caller)
    - health_check()      — lightweight liveness check per agent
    - health_check_all()

Versioning: AgentDefinition.version is sourced from the agent class's
`version` attribute at sync time. Bumping an agent's `version` class
attribute and restarting the API is how a new agent version is rolled
out in Phase 5 (no side-by-side multi-version execution — that level of
agent lifecycle management is a Phase 6/7 concern).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from apps.api.agents import rca_agent, maintenance_agent, compliance_agent, lessons_agent
from apps.api.agents.base_agent import BaseAgent
from apps.api.models.agent import AgentDefinition

logger = logging.getLogger("indusmind.agents.registry")

# In-process registry of agent singletons — this is the actual source of
# truth for EXECUTING an agent. AgentDefinition rows in Postgres are a
# discoverability/administration mirror (enable/disable, health status)
# that routers query for listing without needing a live agent instance.
_AGENTS: dict[str, BaseAgent] = {
    rca_agent.agent_id: rca_agent,
    maintenance_agent.agent_id: maintenance_agent,
    compliance_agent.agent_id: compliance_agent,
    lessons_agent.agent_id: lessons_agent,
}


def sync_agent_definitions(db: Session) -> None:
    """
    Upserts one AgentDefinition row per registered agent. Called once at
    app startup (main.py lifespan) — safe to call repeatedly (idempotent).
    """
    for agent in _AGENTS.values():
        row = db.query(AgentDefinition).filter(AgentDefinition.agent_key == agent.agent_id).first()
        if row is None:
            row = AgentDefinition(
                agent_key=agent.agent_id,
                name=agent.name,
                description=agent.description,
                version=agent.version,
                capabilities=agent.capabilities,
                is_enabled=True,
                health_status="unknown",
            )
            db.add(row)
            logger.info("agent_registered agent_key=%s version=%s", agent.agent_id, agent.version)
        else:
            row.name = agent.name
            row.description = agent.description
            row.version = agent.version
            row.capabilities = agent.capabilities
    db.commit()


def list_agent_definitions(db: Session) -> list[AgentDefinition]:
    return db.query(AgentDefinition).order_by(AgentDefinition.name).all()


def get_agent_definition(db: Session, agent_key: str) -> Optional[AgentDefinition]:
    return db.query(AgentDefinition).filter(AgentDefinition.agent_key == agent_key).first()


def get_agent(db: Session, agent_key: str) -> Optional[BaseAgent]:
    """Resolves an agent_key to its executable instance, honoring the
    enable/disable flag from the registry table."""
    definition = get_agent_definition(db, agent_key)
    if definition is None or not definition.is_enabled:
        return None
    return _AGENTS.get(agent_key)


def get_agent_unchecked(agent_key: str) -> Optional[BaseAgent]:
    """Resolves without the enabled check — used internally by the
    workflow engine once a workflow has already validated participants."""
    return _AGENTS.get(agent_key)


def set_enabled(db: Session, agent_key: str, enabled: bool) -> Optional[AgentDefinition]:
    row = get_agent_definition(db, agent_key)
    if row is None:
        return None
    row.is_enabled = enabled
    db.commit()
    db.refresh(row)
    logger.info("agent_enabled_changed agent_key=%s enabled=%s", agent_key, enabled)
    return row


def health_check(db: Session, agent_key: str) -> dict:
    """
    Lightweight liveness check: confirms the agent instance exists, its
    LangGraph is compiled, and its prompt template loads. Does NOT invoke
    the LLM or any retrieval backend — that's what a real execution is for.
    """
    agent = _AGENTS.get(agent_key)
    checked_at = datetime.now(timezone.utc)
    if agent is None:
        return {"agent_key": agent_key, "status": "error", "checked_at": checked_at, "detail": "not registered"}
    try:
        _ = agent._graph  # compiled StateGraph
        prompt = agent._load_prompt()
        status = "ok" if prompt else "degraded"
        detail = None if prompt else "prompt template missing, using fallback"
    except Exception as exc:  # noqa: BLE001
        status, detail = "error", str(exc)

    row = get_agent_definition(db, agent_key)
    if row is not None:
        row.health_status = status
        row.last_health_check_at = checked_at
        db.commit()

    return {"agent_key": agent_key, "status": status, "checked_at": checked_at, "detail": detail}


def health_check_all(db: Session) -> list[dict]:
    return [health_check(db, key) for key in _AGENTS.keys()]
