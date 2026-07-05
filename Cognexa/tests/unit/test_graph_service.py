"""
tests/unit/test_graph_service.py

Purpose
-------
Unit tests for GraphService, mocking GraphRepository so no real Neo4j
connection is required in CI. Integration tests (real Neo4j via
testcontainers) live in tests/integration/test_graph_api.py.

Dependencies
------------
- pytest
- unittest.mock
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.api.services.graph import GraphService, GraphServiceError, NodeNotFoundError


@pytest.fixture
def mock_repository():
    return MagicMock()


@pytest.fixture
def service(mock_repository):
    return GraphService(repository=mock_repository)


class TestGetAssetGraph:
    def test_returns_subgraph_when_nodes_exist(self, service, mock_repository):
        mock_repository.get_asset_subgraph.return_value = {
            "nodes": [{"id": "1", "label": "Asset", "properties": {"name": "Pump-203"}}],
            "edges": [],
            "center_node_id": "1",
        }
        result = service.get_asset_graph(asset_id="asset-203", depth=1, limit=100)
        assert len(result["nodes"]) == 1
        mock_repository.get_asset_subgraph.assert_called_once_with(
            asset_id="asset-203", depth=1, limit=100
        )

    def test_raises_not_found_when_no_nodes(self, service, mock_repository):
        mock_repository.get_asset_subgraph.return_value = {"nodes": [], "edges": [], "center_node_id": None}
        with pytest.raises(NodeNotFoundError):
            service.get_asset_graph(asset_id="nonexistent", depth=1, limit=100)


class TestExpandNode:
    def test_rejects_invalid_relationship_type(self, service):
        with pytest.raises(GraphServiceError):
            service.expand_node(node_id="1", relationship_types=["NOT_A_REAL_TYPE"], depth=1, limit=50)

    def test_accepts_valid_relationship_type(self, service, mock_repository):
        mock_repository.expand_node.return_value = {"nodes": [], "edges": []}
        service.expand_node(node_id="1", relationship_types=["CAUSED_BY"], depth=1, limit=50)
        mock_repository.expand_node.assert_called_once()


class TestSearch:
    def test_rejects_invalid_label(self, service):
        with pytest.raises(GraphServiceError):
            service.search(query_text="pump", labels=["NotARealLabel"], limit=20)

    def test_returns_results_for_valid_query(self, service, mock_repository):
        mock_repository.search_nodes.return_value = [{"id": "1", "label": "Asset", "properties": {}}]
        results = service.search(query_text="pump", labels=["Asset"], limit=20)
        assert len(results) == 1


class TestSyncIncidentNode:
    def test_creates_incident_and_relationships(self, service, mock_repository):
        mock_repository.upsert_node.return_value = {"id": "n1", "label": "Incident", "properties": {}}
        result = service.sync_incident_node(
            incident_id="inc-1",
            title="Pump seal failure",
            asset_id="asset-203",
            occurred_at_iso="2026-06-01T00:00:00Z",
            document_id="doc-1",
            failure_mode_code="FM-003",
        )
        assert result["label"] == "Incident"
        # INVOLVES (asset), REPORTED_IN (document), CAUSED_BY (failure mode)
        assert mock_repository.upsert_relationship.call_count == 3


class TestStats:
    def test_returns_totals(self, service, mock_repository):
        mock_repository.get_graph_stats.return_value = {
            "node_counts": {"Asset": 10, "Incident": 5},
            "relationship_counts": {"INVOLVES": 5},
            "total_nodes": 15,
            "total_relationships": 5,
        }
        stats = service.stats()
        assert stats["total_nodes"] == 15
