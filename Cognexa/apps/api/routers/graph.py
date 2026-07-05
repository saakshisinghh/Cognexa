"""
apps/api/routers/graph.py

Purpose
-------
HTTP API for Knowledge Graph features: subgraph fetch, expand, search,
stats, similarity, and health. Reuses the existing auth/RBAC dependency
(get_current_user, require_role) from Phase 1 — does not reimplement auth.

Dependencies
------------
- apps/api/services/graph.py
- apps/api/schemas/graph.py
- apps/api/routers/auth.py (assumed to exist — get_current_user, require_role)
- FastAPI

This file is NEW. Registered in main.py with:
    app.include_router(graph_router, prefix="/api/v1/graph", tags=["graph"])
(one-line addition to main.py, shown at the end of this step)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

# Reused from Phase 1 — NOT redefined here.
from apps.api.routers.auth import get_current_user, require_role
from apps.api.schemas.graph import (
    GraphSubgraphResponse,
    GraphExpandRequest,
    GraphSearchRequest,
    GraphStatsResponse,
    GraphHealthResponse,
    SimilarityResult,
)
from apps.api.services.graph import (
    graph_service,
    GraphServiceError,
    NodeNotFoundError,
)

logger = logging.getLogger("indusmind.graph.router")

router = APIRouter()


@router.get("/health", response_model=GraphHealthResponse)
def graph_health():
    """No auth required — used by infra health checks / load balancers."""
    result = graph_service.health()
    if not result["connected"]:
        # 503 so orchestrators (k8s/docker healthcheck) correctly mark unhealthy
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result)
    return result


@router.get("/assets/{asset_id}/subgraph", response_model=GraphSubgraphResponse)
def get_asset_subgraph(
    asset_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    limit: int = Query(default=100, ge=1, le=500),
    current_user=Depends(get_current_user),
):
    """Powers the 'Graph' tab on Asset 360 (apps/web/app/assets/[id]/)."""
    try:
        return graph_service.get_asset_graph(asset_id=asset_id, depth=depth, limit=limit)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GraphServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error fetching subgraph for asset_id=%s", asset_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="graph_query_failed") from exc


@router.post("/expand", response_model=GraphSubgraphResponse)
def expand_node(
    payload: GraphExpandRequest,
    current_user=Depends(get_current_user),
):
    """Powers the 'Expand Node' action in the Graph Explorer."""
    try:
        result = graph_service.expand_node(
            node_id=payload.node_id,
            relationship_types=payload.relationship_types,
            depth=payload.depth,
            limit=payload.limit,
        )
        return {**result, "center_node_id": payload.node_id}
    except GraphServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error expanding node_id=%s", payload.node_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="graph_expand_failed") from exc


@router.post("/search")
def search_graph(
    payload: GraphSearchRequest,
    current_user=Depends(get_current_user),
):
    """Powers 'Search Asset' in the Graph Sidebar."""
    try:
        results = graph_service.search(query_text=payload.query, labels=payload.labels, limit=payload.limit)
        return {"results": results, "count": len(results)}
    except GraphServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/stats", response_model=GraphStatsResponse)
def graph_stats(current_user=Depends(get_current_user)):
    """Powers the Graph Statistics panel."""
    try:
        return graph_service.stats()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute graph stats")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="graph_stats_failed") from exc


@router.get("/assets/{asset_id}/similar", response_model=list[SimilarityResult])
def get_similar_assets(
    asset_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    current_user=Depends(get_current_user),
):
    """Powers the Similarity Relationships feature in the Asset 360 Graph tab."""
    return graph_service.similar_assets(asset_id=asset_id, limit=limit)


@router.post("/admin/resync", status_code=status.HTTP_202_ACCEPTED)
def trigger_full_resync(
    current_user=Depends(require_role("admin")),  # admin-only, reuses existing RBAC dependency
):
    """
    Manual full reconciliation trigger (e.g. after a Neo4j restore).
    Enqueues the existing Celery tasks rather than blocking the request.
    """
    from apps.api.pipelines.graph_sync import apply_schema_task, seed_failure_modes_task

    apply_schema_task.delay()
    seed_failure_modes_task.delay()
    return {"status": "resync_enqueued"}
