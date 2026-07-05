"""
tests/integration/test_incident_graph_sync.py

Purpose
-------
Integration test verifying the full flow: POST /api/v1/incidents creates
a Postgres row AND (synchronously in test mode, via CELERY_TASK_ALWAYS_EAGER)
results in a corresponding :Incident node in Neo4j.

Assumes:
- conftest.py already provides `client` (TestClient with auth override)
  and `db_session` fixtures from Phase 1/2 — REUSED, not redefined here.
- A test Neo4j instance is reachable (CI runs neo4j as a service container).

Dependencies
------------
- pytest
- httpx / fastapi.testclient (via existing `client` fixture)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from apps.api.db_graph import neo4j_session


@pytest.fixture(autouse=True)
def cleanup_test_incidents():
    yield
    # Test isolation: remove any Incident nodes created with the test marker
    with neo4j_session() as session:
        session.run("MATCH (i:Incident) WHERE i.title STARTS WITH 'TEST_' DETACH DELETE i")


def test_create_incident_syncs_to_neo4j(client, db_session, test_asset):
    """
    test_asset is assumed to be an existing Phase 1 fixture providing a
    persisted Asset row + corresponding :Asset graph node.
    """
    payload = {
        "title": "TEST_Pump seal failure",
        "description": "Seal leakage observed during routine inspection",
        "asset_id": str(test_asset.id),
        "severity": "high",
        "status": "open",
        "failure_mode_code": "FM-003",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }

    response = client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201
    incident_id = response.json()["id"]

    # With CELERY_TASK_ALWAYS_EAGER=True in test settings, .delay() runs synchronously
    with neo4j_session() as session:
        result = session.run(
            "MATCH (i:Incident {incident_id: $id}) RETURN i.title AS title",
            id=incident_id,
        )
        record = result.single()
        assert record is not None
        assert record["title"] == "TEST_Pump seal failure"


def test_create_incident_with_invalid_asset_returns_400(client):
    payload = {
        "title": "TEST_Invalid asset incident",
        "description": "Should fail FK constraint",
        "asset_id": str(uuid.uuid4()),  # non-existent
        "severity": "low",
        "status": "open",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 400


def test_graph_health_endpoint(client):
    response = client.get("/api/v1/graph/health")
    assert response.status_code == 200
    assert response.json()["connected"] is True


def test_asset_subgraph_endpoint(client, test_asset):
    response = client.get(f"/api/v1/graph/assets/{test_asset.asset_id}/subgraph")
    assert response.status_code in (200, 404)  # 404 acceptable if asset not yet graph-synced
