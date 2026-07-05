"""
apps/api/services/graph.py

Purpose
-------
Business-logic layer for Knowledge Graph features. Sits between
graph_repository.py (raw Cypher) and routers/graph.py (HTTP). This is
the file referenced as "apps/api/services/graph.py" in the roadmap.

Dependencies
------------
- apps/api/services/graph_repository.py
- apps/api/db_graph.py (health check passthrough)
- apps/api/ontology/schema.py

This file is NEW.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from apps.api.db_graph import (
    check_neo4j_health,
    get_neo4j_driver,
)
from apps.api.ontology.schema import NodeLabel, RelationshipType
from apps.api.services.graph_repository import graph_repository, DuplicateNodeError

logger = logging.getLogger("indusmind.graph.service")


class GraphServiceError(Exception):
    """Base exception for graph service failures, caught by the router."""


class NodeNotFoundError(GraphServiceError):
    pass


class GraphService:
    def __init__(self, repository=graph_repository):
        self.repository = repository

    # ------------------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        return check_neo4j_health()

    # ------------------------------------------------------------------
    def get_asset_graph(self, asset_id: str, depth: int = 1, limit: int = 100) -> Dict[str, Any]:
        subgraph = self.repository.get_asset_subgraph(asset_id=asset_id, depth=depth, limit=limit)
        if not subgraph["nodes"]:
            raise NodeNotFoundError(f"No graph data found for asset_id={asset_id}")
        return subgraph

    # ------------------------------------------------------------------
    def expand_node(self, node_id: str, relationship_types: Optional[List[str]],
                     depth: int, limit: int) -> Dict[str, Any]:
        if relationship_types:
            valid = {r.value for r in RelationshipType}
            invalid = set(relationship_types) - valid
            if invalid:
                raise GraphServiceError(f"Invalid relationship types: {invalid}")
        return self.repository.expand_node(node_id, relationship_types, depth, limit)

    # ------------------------------------------------------------------
    def search(self, query_text: str, labels: Optional[List[str]], limit: int) -> List[Dict[str, Any]]:
        if labels:
            valid = {l.value for l in NodeLabel}
            invalid = set(labels) - valid
            if invalid:
                raise GraphServiceError(f"Invalid node labels: {invalid}")
        return self.repository.search_nodes(query_text, labels, limit)

    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        return self.repository.get_graph_stats()

    # ------------------------------------------------------------------
    def similar_assets(self, asset_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        results = self.repository.find_similar_assets(asset_id, limit)
        if not results:
            logger.info("No precomputed similarity edges for asset_id=%s — "
                        "run the Celery similarity job to populate them", asset_id)
        return results

    # ------------------------------------------------------------------
    # Used by graph_sync.py — wraps repository upserts with domain logic
    # ------------------------------------------------------------------
    def sync_asset_node(self, asset_id: str, name: str, site_id: Optional[str] = None,
                         extra_properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        properties = {"name": name, **(extra_properties or {})}
        try:
            node = self.repository.upsert_node(NodeLabel.ASSET, "asset_id", asset_id, properties)
        except DuplicateNodeError as exc:
            raise GraphServiceError(f"Failed to sync asset {asset_id}: {exc}") from exc

        if site_id:
            self.repository.upsert_node(NodeLabel.SITE, "site_id", site_id, {})
            self.repository.upsert_relationship(
                NodeLabel.ASSET, "asset_id", asset_id,
                NodeLabel.SITE, "site_id", site_id,
                RelationshipType.LOCATED_AT,
            )
        return node

    def sync_incident_node(self, incident_id: str, title: str, asset_id: str,
                            occurred_at_iso: str, document_id: Optional[str] = None,
                            failure_mode_code: Optional[str] = None,
                            extra_properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        properties = {
            "title": title,
            "occurred_at": occurred_at_iso,
            **(extra_properties or {}),
        }
        node = self.repository.upsert_node(NodeLabel.INCIDENT, "incident_id", incident_id, properties)

        self.repository.upsert_relationship(
            NodeLabel.INCIDENT, "incident_id", incident_id,
            NodeLabel.ASSET, "asset_id", asset_id,
            RelationshipType.INVOLVES,
        )

        if document_id:
            self.repository.upsert_node(NodeLabel.DOCUMENT, "document_id", document_id, {})
            self.repository.upsert_relationship(
                NodeLabel.INCIDENT, "incident_id", incident_id,
                NodeLabel.DOCUMENT, "document_id", document_id,
                RelationshipType.REPORTED_IN,
            )

        if failure_mode_code:
            self.repository.upsert_relationship(
                NodeLabel.INCIDENT, "incident_id", incident_id,
                NodeLabel.FAILURE_MODE, "code", failure_mode_code,
                RelationshipType.CAUSED_BY,
            )

        return node


graph_service = GraphService()
# ------------------------------------------------------------------
# Compatibility wrapper for retrieval modules
# ------------------------------------------------------------------

def get_neo4j_driver():
    """
    Returns the shared Neo4j driver singleton.

    This wrapper allows other modules (such as
    retrieval/graph_retriever.py) to import the driver from
    apps.api.services.graph while the actual implementation
    remains inside db_graph.py.
    """
    from apps.api.db_graph import get_neo4j_driver as _driver
    return _driver()