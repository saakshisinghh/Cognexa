"""
apps/api/schemas/graph.py

Purpose
-------
Pydantic v2 request/response models for:
  1. Incident CRUD (apps/api/routers/incidents.py would import these —
     incidents.py itself is not re-created here since incident CRUD
     routing already had a stub from the documents.py pattern; only the
     graph-aware fields are new)
  2. Graph query API (apps/api/routers/graph.py)

Dependencies
------------
- pydantic v2
- apps/api/models/incident.py (enums reused, not redefined)

This file is NEW.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.api.models.incident import IncidentSeverity, IncidentStatus


# ---------------------------------------------------------------------------
# Incident schemas
# ---------------------------------------------------------------------------
class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=10)
    asset_id: UUID
    document_id: Optional[UUID] = None
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    status: IncidentStatus = IncidentStatus.OPEN
    failure_mode_code: Optional[str] = None
    occurred_at: datetime

    @field_validator("failure_mode_code")
    @classmethod
    def validate_failure_mode_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("FM-"):
            raise ValueError("failure_mode_code must follow the 'FM-xxx' ontology format")
        return v


class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None, min_length=10)
    severity: Optional[IncidentSeverity] = None
    status: Optional[IncidentStatus] = None
    failure_mode_code: Optional[str] = None


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    asset_id: UUID
    document_id: Optional[UUID]
    reported_by: Optional[UUID]
    severity: IncidentSeverity
    status: IncidentStatus
    failure_mode_code: Optional[str]
    occurred_at: datetime
    graph_sync_status: str
    graph_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Graph query schemas
# ---------------------------------------------------------------------------
class GraphNode(BaseModel):
    id: str                      # Neo4j elementId, stable across the response
    label: str                   # NodeLabel value, e.g. "Asset"
    properties: Dict[str, Any]


class GraphEdge(BaseModel):
    id: str
    source: str                  # GraphNode.id
    target: str                  # GraphNode.id
    type: str                    # RelationshipType value
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphSubgraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    center_node_id: Optional[str] = None


class GraphExpandRequest(BaseModel):
    node_id: str
    relationship_types: Optional[List[str]] = None
    depth: int = Field(default=1, ge=1, le=3)
    limit: int = Field(default=50, ge=1, le=200)


class GraphSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    labels: Optional[List[str]] = None
    limit: int = Field(default=20, ge=1, le=100)


class GraphStatsResponse(BaseModel):
    node_counts: Dict[str, int]
    relationship_counts: Dict[str, int]
    total_nodes: int
    total_relationships: int
    last_sync_at: Optional[datetime] = None


class GraphHealthResponse(BaseModel):
    connected: bool
    database: str
    error: Optional[str] = None


class SimilarityResult(BaseModel):
    node_id: str
    label: str
    properties: Dict[str, Any]
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    shared_relationships: int = 0
