"""
apps/api/agents/__init__.py

Phase 5 — Agentic AI Platform.

Exposes the four concrete agent singletons. Registration into the
dynamic agent registry (enable/disable, versioning, capability
discovery, health checks) happens in
apps/api/services/agent_registry.py, which imports from here — this
module intentionally does NOT self-register, keeping "define an agent"
and "make it discoverable" as separate concerns.
"""
from apps.api.agents.rca_agent import rca_agent, RCAAgent
from apps.api.agents.maintenance_agent import maintenance_agent, MaintenanceAgent
from apps.api.agents.compliance_agent import compliance_agent, ComplianceAgent
from apps.api.agents.lessons_agent import lessons_agent, LessonsLearnedAgent

__all__ = [
    "rca_agent", "RCAAgent",
    "maintenance_agent", "MaintenanceAgent",
    "compliance_agent", "ComplianceAgent",
    "lessons_agent", "LessonsLearnedAgent",
]
