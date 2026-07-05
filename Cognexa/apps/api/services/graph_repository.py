"""
apps/api/services/graph_repository.py

Purpose
-------
Repository-pattern data-access layer for Neo4j. Holds ALL raw Cypher.
graph_service.py (Step 5) depends on this and never writes Cypher itself,
matching the Repository Pattern used by the Phase 1/2 SQLAlchemy repos.

Dependencies
------------
- apps/api/db_graph.py (neo4j_session)
- apps/api/ontology/schema.py (NodeLabel, RelationshipType)

This file is NEW.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from neo4j.exceptions import ConstraintError, Neo4jError

from apps.api.db_graph import neo4j_session
from apps.api.ontology.schema import NodeLabel, RelationshipType

logger = logging.getLogger("indusmind.graph.repository")


class DuplicateNodeError(Exception):
    """Raised when a uniqueness constraint is violated on node creation."""


class GraphRepository:
    """Pure data-access layer. No business rules live here."""

    # ------------------------------------------------------------------
    # Node upsert (idempotent — used by graph_sync.py)
    # ------------------------------------------------------------------
    def upsert_node(self, label: NodeLabel, key_field: str, key_value: str,
                     properties: Dict[str, Any]) -> Dict[str, Any]:
        query = (
            f"MERGE (n:{label.value} {{{key_field}: $key_value}}) "
            "SET n += $properties, n.updated_at = datetime() "
            "RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties"
        )
        try:
            with neo4j_session() as session:
                result = session.run(query, key_value=key_value, properties=properties)
                record = result.single()
                if record is None:
                    raise Neo4jError("MERGE returned no record")
                return {"id": record["id"], "label": record["labels"][0], "properties": record["properties"]}
        except ConstraintError as exc:
            logger.warning("Constraint violation upserting %s:%s — %s", label.value, key_value, exc)
            raise DuplicateNodeError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Relationship upsert (idempotent)
    # ------------------------------------------------------------------
    def upsert_relationship(self, from_label: NodeLabel, from_key_field: str, from_key_value: str,
                             to_label: NodeLabel, to_key_field: str, to_key_value: str,
                             rel_type: RelationshipType, properties: Optional[Dict[str, Any]] = None) -> bool:
        query = (
            f"MATCH (a:{from_label.value} {{{from_key_field}: $from_value}}) "
            f"MATCH (b:{to_label.value} {{{to_key_field}: $to_value}}) "
            f"MERGE (a)-[r:{rel_type.value}]->(b) "
            "SET r += $properties, r.updated_at = datetime() "
            "RETURN type(r) AS rel_type"
        )
        with neo4j_session() as session:
            result = session.run(
                query,
                from_value=from_key_value,
                to_value=to_key_value,
                properties=properties or {},
            )
            return result.single() is not None

    # ------------------------------------------------------------------
    # Subgraph fetch — Asset Graph Tab / Graph Explorer initial load
    # ------------------------------------------------------------------
    def get_asset_subgraph(self, asset_id: str, depth: int = 1, limit: int = 100) -> Dict[str, List[Dict]]:
        query = (
            "MATCH (center:Asset {asset_id: $asset_id}) "
            f"CALL apoc.path.subgraphAll(center, {{maxLevel: $depth, limit: $limit}}) "
            "YIELD nodes, relationships "
            "RETURN nodes, relationships, elementId(center) AS center_id"
        )
        with neo4j_session() as session:
            result = session.run(query, asset_id=asset_id, depth=depth, limit=limit)
            record = result.single()
            if record is None:
                return {"nodes": [], "edges": [], "center_node_id": None}
            return self._serialize_subgraph(record["nodes"], record["relationships"], record["center_id"])

    # ------------------------------------------------------------------
    # Node expand — "Expand Node" frontend action
    # ------------------------------------------------------------------
    def expand_node(self, node_id: str, relationship_types: Optional[List[str]], depth: int, limit: int) -> Dict:
        rel_filter = "|".join(relationship_types) if relationship_types else None
        rel_clause = f":{rel_filter}" if rel_filter else ""
        query = (
            f"MATCH (center) WHERE elementId(center) = $node_id "
            f"CALL apoc.path.subgraphAll(center, {{relationshipFilter: $rel_clause, maxLevel: $depth, limit: $limit}}) "
            "YIELD nodes, relationships "
            "RETURN nodes, relationships"
        )
        with neo4j_session() as session:
            result = session.run(
                query, node_id=node_id, rel_clause=rel_clause if rel_clause else None,
                depth=depth, limit=limit,
            )
            record = result.single()
            if record is None:
                return {"nodes": [], "edges": []}
            return self._serialize_subgraph(record["nodes"], record["relationships"], node_id)

    # ------------------------------------------------------------------
    # Search nodes by text (Graph Explorer search box)
    # ------------------------------------------------------------------
    def search_nodes(self, query_text: str, labels: Optional[List[str]], limit: int) -> List[Dict]:
        label_clause = "|".join(labels) if labels else "Asset|Equipment|Incident|FailureMode|Document|Person"
        cypher = (
            f"MATCH (n:{label_clause}) "
            "WHERE toLower(n.name) CONTAINS toLower($q) OR toLower(coalesce(n.title, '')) CONTAINS toLower($q) "
            "RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties "
            "LIMIT $limit"
        )
        with neo4j_session() as session:
            result = session.run(cypher, q=query_text, limit=limit)
            return [
                {"id": r["id"], "label": r["labels"][0], "properties": r["properties"]}
                for r in result
            ]

    # ------------------------------------------------------------------
    # Graph statistics — Graph Statistics panel
    # ------------------------------------------------------------------
    def get_graph_stats(self) -> Dict[str, Any]:
        node_query = "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count"
        rel_query = "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count"
        with neo4j_session() as session:
            node_counts = {r["label"]: r["count"] for r in session.run(node_query)}
            rel_counts = {r["type"]: r["count"] for r in session.run(rel_query)}
        return {
            "node_counts": node_counts,
            "relationship_counts": rel_counts,
            "total_nodes": sum(node_counts.values()),
            "total_relationships": sum(rel_counts.values()),
        }

    # ------------------------------------------------------------------
    # Similarity relationships — computed + persisted by graph_sync.py
    # ------------------------------------------------------------------
    def create_similarity_edge(self, node_a_id: str, node_b_id: str, score: float, shared: int) -> None:
        query = (
            "MATCH (a) WHERE elementId(a) = $a_id "
            "MATCH (b) WHERE elementId(b) = $b_id "
            "MERGE (a)-[r:SIMILAR_TO]-(b) "
            "SET r.score = $score, r.shared_relationships = $shared, r.computed_at = datetime()"
        )
        with neo4j_session() as session:
            session.run(query, a_id=node_a_id, b_id=node_b_id, score=score, shared=shared)

    def find_similar_assets(self, asset_id: str, limit: int = 10) -> List[Dict]:
        query = (
            "MATCH (a:Asset {asset_id: $asset_id})-[r:SIMILAR_TO]-(b:Asset) "
            "RETURN elementId(b) AS id, labels(b) AS labels, properties(b) AS properties, "
            "r.score AS score, r.shared_relationships AS shared "
            "ORDER BY r.score DESC LIMIT $limit"
        )
        with neo4j_session() as session:
            result = session.run(query, asset_id=asset_id, limit=limit)
            return [
                {
                    "id": r["id"], "label": r["labels"][0], "properties": r["properties"],
                    "similarity_score": r["score"], "shared_relationships": r["shared"],
                }
                for r in result
            ]

    # ------------------------------------------------------------------
    # Internal serialization helper
    # ------------------------------------------------------------------
    @staticmethod
    def _serialize_subgraph(nodes, relationships, center_id) -> Dict[str, List[Dict]]:
        node_list = [
            {"id": n.element_id, "label": list(n.labels)[0] if n.labels else "Unknown", "properties": dict(n)}
            for n in nodes
        ]
        edge_list = [
            {
                "id": r.element_id,
                "source": r.start_node.element_id,
                "target": r.end_node.element_id,
                "type": r.type,
                "properties": dict(r),
            }
            for r in relationships
        ]
        return {"nodes": node_list, "edges": edge_list, "center_node_id": center_id}


graph_repository = GraphRepository()
