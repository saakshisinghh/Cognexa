"""
apps/api/ontology/schema.py

Purpose
-------
Single source of truth for the Knowledge Graph ontology: node labels,
relationship types, and the Cypher DDL (constraints + indexes) that must
exist in Neo4j before any sync job writes data. Keeping this as typed
Python constants (not magic strings scattered across graph.py) prevents
typos from silently creating duplicate relationship types.

Dependencies
------------
- apps/api/db_graph.py (neo4j_session)

This file is NEW.
"""

from __future__ import annotations

from enum import Enum
from typing import List

from apps.api.db_graph import neo4j_session


class NodeLabel(str, Enum):
    ASSET = "Asset"
    EQUIPMENT = "Equipment"
    FAILURE = "Failure"
    FAILURE_MODE = "FailureMode"
    INCIDENT = "Incident"
    INSPECTION = "Inspection"
    PERSON = "Person"
    DOCUMENT = "Document"
    COMPLIANCE_RULE = "ComplianceRule"
    SITE = "Site"


class RelationshipType(str, Enum):
    PART_OF = "PART_OF"                  # Equipment -> Asset
    LOCATED_AT = "LOCATED_AT"            # Asset -> Site
    CAUSED_BY = "CAUSED_BY"              # Incident -> Failure
    HAS_FAILURE_MODE = "HAS_FAILURE_MODE"  # Failure -> FailureMode
    INSPECTED_BY = "INSPECTED_BY"        # Inspection -> Person
    REPORTED_IN = "REPORTED_IN"          # Incident -> Document
    INVOLVES = "INVOLVES"                # Incident -> Asset
    AFFECTS = "AFFECTS"                  # Inspection -> Asset
    SIMILAR_TO = "SIMILAR_TO"            # Asset|Incident -> Asset|Incident (weighted)
    SUBJECT_TO = "SUBJECT_TO"            # Asset -> ComplianceRule
    AUTHORED_BY = "AUTHORED_BY"          # Document -> Person


# ---------------------------------------------------------------------------
# Cypher DDL — uniqueness constraints (also create backing indexes in Neo4j)
# ---------------------------------------------------------------------------
CONSTRAINT_STATEMENTS: List[str] = [
    "CREATE CONSTRAINT asset_id_unique IF NOT EXISTS "
    "FOR (a:Asset) REQUIRE a.asset_id IS UNIQUE",

    "CREATE CONSTRAINT equipment_id_unique IF NOT EXISTS "
    "FOR (e:Equipment) REQUIRE e.equipment_id IS UNIQUE",

    "CREATE CONSTRAINT incident_id_unique IF NOT EXISTS "
    "FOR (i:Incident) REQUIRE i.incident_id IS UNIQUE",

    "CREATE CONSTRAINT failure_id_unique IF NOT EXISTS "
    "FOR (f:Failure) REQUIRE f.failure_id IS UNIQUE",

    "CREATE CONSTRAINT failure_mode_code_unique IF NOT EXISTS "
    "FOR (fm:FailureMode) REQUIRE fm.code IS UNIQUE",

    "CREATE CONSTRAINT inspection_id_unique IF NOT EXISTS "
    "FOR (i:Inspection) REQUIRE i.inspection_id IS UNIQUE",

    "CREATE CONSTRAINT person_id_unique IF NOT EXISTS "
    "FOR (p:Person) REQUIRE p.person_id IS UNIQUE",

    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.document_id IS UNIQUE",

    "CREATE CONSTRAINT compliance_rule_id_unique IF NOT EXISTS "
    "FOR (c:ComplianceRule) REQUIRE c.rule_id IS UNIQUE",

    "CREATE CONSTRAINT site_id_unique IF NOT EXISTS "
    "FOR (s:Site) REQUIRE s.site_id IS UNIQUE",
]

INDEX_STATEMENTS: List[str] = [
    "CREATE INDEX asset_name_idx IF NOT EXISTS FOR (a:Asset) ON (a.name)",
    "CREATE INDEX incident_date_idx IF NOT EXISTS FOR (i:Incident) ON (i.occurred_at)",
    "CREATE INDEX failure_mode_category_idx IF NOT EXISTS FOR (fm:FailureMode) ON (fm.category)",
]


def apply_graph_schema() -> dict:
    """
    Idempotent — safe to call on every app startup. `IF NOT EXISTS` makes
    every statement a no-op on subsequent runs.

    Returns a summary dict for logging / the /graph/health endpoint.
    """
    applied = []
    failed = []
    with neo4j_session() as session:
        for stmt in CONSTRAINT_STATEMENTS + INDEX_STATEMENTS:
            try:
                session.run(stmt)
                applied.append(stmt)
            except Exception as exc:  # noqa: BLE001
                failed.append({"statement": stmt, "error": str(exc)})
    return {"applied": len(applied), "failed": failed}
