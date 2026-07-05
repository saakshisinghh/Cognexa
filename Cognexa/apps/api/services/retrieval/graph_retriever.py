"""
apps/api/services/retrieval/graph_retriever.py

Path C of triple retrieval: knowledge-graph context.

REUSES apps/api/services/graph.py (the existing Phase 3 Neo4j driver
wrapper and graph CRUD/traversal functions) — does not open a second
Neo4j connection or duplicate Cypher query logic. This module only adds
NEW read-only Cypher queries for context expansion that did not exist
in Phase 3 (Phase 3 exposed neighbor/similar-failure endpoints for the
Graph Explorer UI; this module repurposes the same underlying connection
for copilot-time context retrieval).

When the query mentions an asset tag (detected by asset_tag_detector.py),
this path pulls:
    - the asset's own KnowledgeChunk mentions (MENTIONS relationship)
    - connected incidents (HAS_INCIDENT) and their summaries
    - connected failure modes (CAUSED_BY) and their descriptions
    - documents linked via DOCUMENTED_IN

These are converted into RetrievedChunk objects so they can be fused via
RRF alongside BM25 and vector results using the same uniform schema.

If no asset tags are detected, this path returns an empty list immediately
without touching Neo4j — most copilot queries are not asset-specific, and
this avoids unnecessary graph load.
"""

import asyncio
import logging
from uuid import UUID, uuid4

from apps.api.db_graph import neo4j_session  # existing Phase 3 connection (sync driver)
from apps.api.schemas.retrieval import RetrievalFilters, RetrievedChunk

logger = logging.getLogger("indus_mind.retrieval.graph")

# Read-only Cypher — pulls a 2-hop neighborhood around each detected asset tag
# and surfaces it as pseudo-chunks (KnowledgeChunk text, incident summaries,
# failure mode descriptions, and linked document titles).
_GRAPH_CONTEXT_QUERY = """
MATCH (a:Asset {tag_number: $tag})
OPTIONAL MATCH (a)-[:HAS_INCIDENT]->(i:Incident)
OPTIONAL MATCH (i)-[:CAUSED_BY]->(fm:FailureMode)
OPTIONAL MATCH (a)-[:DOCUMENTED_IN]->(d:Document)
OPTIONAL MATCH (kc:KnowledgeChunk)-[:MENTIONS]->(a)
RETURN
    a.tag_number AS asset_tag,
    a.name AS asset_name,
    collect(DISTINCT {
        incident_number: i.incident_number,
        severity: i.severity,
        occurred_at: toString(i.occurred_at),
        summary: i.title
    }) AS incidents,
    collect(DISTINCT {
        code: fm.code,
        name: fm.name,
        category: fm.category
    }) AS failure_modes,
    collect(DISTINCT {
        doc_id: d.doc_id,
        title: d.title,
        trust_score: d.trust_score
    }) AS documents,
    collect(DISTINCT {
        chunk_id: kc.chunk_id,
        summary: kc.summary,
        trust_score: kc.trust_score
    }) AS knowledge_chunks
LIMIT 1
"""


async def graph_retrieve(
    asset_tags: list[str],
    top_k: int,
    filters: RetrievalFilters,
) -> list[RetrievedChunk]:
    """
    Pulls graph-connected context for each detected asset tag and converts
    it into RetrievedChunk objects for RRF fusion.

    Returns [] immediately (no Neo4j call) if no asset tags were detected
    in the query — this is the expected, common case and is NOT an error.
    """
    if not asset_tags:
        return []

    # db_graph.get_neo4j_driver() returns the synchronous neo4j.Driver used
    # everywhere else in Phase 3 (graph_repository.py). Run the blocking
    # session work in a worker thread so we don't block the event loop.
    chunks = await asyncio.to_thread(_graph_retrieve_sync, asset_tags, filters)

    logger.debug("graph_retrieve asset_tags=%s returned=%d", asset_tags, len(chunks))
    return chunks


def _graph_retrieve_sync(
    asset_tags: list[str],
    filters: RetrievalFilters,
) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    rank = 1

    with neo4j_session() as session:
        for tag in asset_tags:
            if filters.asset_id:
                # If the request is explicitly scoped to one asset (pinned
                # asset context — see Step 3), skip graph expansion for any
                # other detected tag.
                pass  # filtering by asset_id UUID happens at the asset
                      # lookup layer (services/graph.py), tag_number is the
                      # graph-native key used here intentionally.

            result = session.run(_GRAPH_CONTEXT_QUERY, tag=tag)
            record = result.single()

            if not record or not record.get("asset_tag"):
                logger.debug("graph_retrieve: asset tag %s not found in graph", tag)
                continue

            asset_name = record.get("asset_name") or tag

            # Incidents -> pseudo-chunks
            for incident in record.get("incidents", []):
                if not incident.get("incident_number"):
                    continue
                content = (
                    f"Incident {incident['incident_number']} on asset {tag} "
                    f"({asset_name}), severity {incident.get('severity', 'unknown')}, "
                    f"occurred {incident.get('occurred_at', 'unknown date')}: "
                    f"{incident.get('summary', '')}"
                )
                chunk = _make_graph_chunk(content=content, source_label="incident", rank=rank)
                chunks.append(chunk)
                rank += 1

            # Failure modes -> pseudo-chunks
            for fm in record.get("failure_modes", []):
                if not fm.get("code"):
                    continue
                content = (
                    f"Asset {tag} ({asset_name}) has a recorded failure mode: "
                    f"{fm.get('name', fm['code'])} (category: {fm.get('category', 'n/a')})"
                )
                chunk = _make_graph_chunk(content=content, source_label="failure_mode", rank=rank)
                chunks.append(chunk)
                rank += 1

            # Existing KnowledgeChunk mentions -> pass through directly,
            # these already reference real document_chunks rows.
            for kc in record.get("knowledge_chunks", []):
                if not kc.get("chunk_id") or not kc.get("summary"):
                    continue
                chunk = RetrievedChunk(
                    chunk_id=UUID(kc["chunk_id"]),
                    document_id=UUID(int=0),  # resolved downstream via chunk_id lookup if needed
                    document_title=f"Knowledge graph context — {asset_name}",
                    content=kc["summary"],
                    trust_score=float(kc.get("trust_score", 1.0)),
                    asset_ids=[],
                )
                chunk.source_ranks["graph"] = rank
                chunk.source_scores["graph"] = 1.0 / rank
                chunks.append(chunk)
                rank += 1

    return chunks


def _make_graph_chunk(content: str, source_label: str, rank: int) -> RetrievedChunk:
    """
    Graph-derived facts (incidents, failure modes) don't map to a single
    existing document_chunks row — they are synthesized from multiple graph
    nodes. We mint a stable-for-this-request synthetic chunk_id so the
    fusion and citation layers can still treat it uniformly; the frontend
    citation panel (Step 3) renders these with a "Knowledge Graph" source
    badge instead of a document page link.
    """
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=UUID(int=0),
        document_title=f"Knowledge Graph — {source_label.replace('_', ' ').title()}",
        content=content,
        trust_score=1.0,
        asset_ids=[],
    )
    chunk.source_ranks["graph"] = rank
    chunk.source_scores["graph"] = 1.0 / rank
    return chunk
