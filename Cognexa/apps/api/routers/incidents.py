"""
apps/api/routers/incidents.py

Purpose
-------
Incident Management CRUD API. Postgres is the system of record; every
create/update enqueues apps.api.pipelines.graph_sync.sync_incident_task
so the Neo4j graph stays eventually-consistent without blocking the
HTTP response.

Dependencies
------------
- apps/api/db.py (get_db — existing Phase 1 dependency)
- apps/api/routers/auth.py (get_current_user — existing Phase 1 dependency)
- apps/api/models/incident.py
- apps/api/schemas/graph.py (IncidentCreate, IncidentUpdate, IncidentResponse)
- apps/api/pipelines/graph_sync.py

This file is NEW. Registered in main.py with:
    app.include_router(incidents_router, prefix="/api/v1/incidents", tags=["incidents"])
"""

from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.db import get_db  # existing Phase 1 dependency
from apps.api.routers.auth import get_current_user  # existing Phase 1 dependency
from apps.api.models.incident import Incident
from apps.api.schemas.graph import IncidentCreate, IncidentUpdate, IncidentResponse

logger = logging.getLogger("indusmind.incidents.router")

router = APIRouter()


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    incident = Incident(
        title=payload.title,
        description=payload.description,
        asset_id=payload.asset_id,
        document_id=payload.document_id,
        reported_by=current_user.id,
        severity=payload.severity,
        status=payload.status,
        failure_mode_code=payload.failure_mode_code,
        occurred_at=payload.occurred_at,
        graph_sync_status="pending",
    )
    db.add(incident)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Integrity error creating incident: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid asset_id, document_id, or duplicate incident",
        ) from exc
    db.refresh(incident)

    # Async graph sync — import here to avoid circular import at module load
    from apps.api.pipelines.graph_sync import sync_incident_task

    sync_incident_task.delay(str(incident.id))

    return incident


@router.get("", response_model=List[IncidentResponse])
def list_incidents(
    asset_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Incident)
    if asset_id:
        query = query.filter(Incident.asset_id == asset_id)
    if status_filter:
        query = query.filter(Incident.status == status_filter)
    return query.order_by(Incident.occurred_at.desc()).offset(offset).limit(limit).all()


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.patch("/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(incident, field, value)
    incident.graph_sync_status = "pending"

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Update violates a constraint") from exc
    db.refresh(incident)

    from apps.api.pipelines.graph_sync import sync_incident_task

    sync_incident_task.delay(str(incident.id))

    return incident


@router.delete("/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    db.delete(incident)
    db.commit()

    # Best-effort graph cleanup — non-blocking, logged but not retried
    # aggressively since the Postgres delete is the source of truth.
    from apps.api.db_graph import neo4j_session

    try:
        with neo4j_session() as session:
            session.run(
                "MATCH (i:Incident {incident_id: $id}) DETACH DELETE i",
                id=str(incident_id),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to delete graph node for incident_id=%s — will be orphaned until next resync", incident_id)

    return None
