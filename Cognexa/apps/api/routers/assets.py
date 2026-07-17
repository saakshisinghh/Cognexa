"""
Assets Router — Industrial asset management with linked documents.
"""
from __future__ import annotations
import logging
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from apps.api.db import get_db
from apps.api.models import Asset, Document, User, DocumentStatus
from apps.api.routers.auth import get_current_user, require_engineer_or_admin
from apps.api.schemas import AssetCreate, AssetUpdate, AssetResponse, AssetListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assets", tags=["Assets"])


def _asset_to_response(asset: Asset, db: Session) -> AssetResponse:
    doc_count = db.query(Document).filter(Document.asset_id == asset.id).count()
    return AssetResponse(
        id=asset.id,
        name=asset.name,
        description=asset.description,
        location=asset.location,
        asset_type=asset.asset_type,
        owner_id=asset.owner_id,
        tags=asset.tags or [],
        # FIX: was `asset.metadata` — on a SQLAlchemy declarative model,
        # `metadata` is a RESERVED class attribute (the table's MetaData
        # registry), not the JSON column. The column is declared as
        # `extra_metadata = Column("metadata", JSON, ...)` specifically to
        # avoid this collision — the Python attribute is `extra_metadata`,
        # only the underlying DB column is named "metadata". Reading
        # `asset.metadata` silently returned the wrong object (a MetaData
        # instance, not the stored dict), which then failed Pydantic
        # validation against AssetResponse.metadata: dict — causing every
        # GET /assets response to fail serialization.
        metadata=asset.extra_metadata or {},
        health_status=asset.health_status,
        is_active=asset.is_active,
        document_count=doc_count,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.post("", response_model=AssetResponse, status_code=201)
def create_asset(
    payload: AssetCreate,
    current_user: User = Depends(require_engineer_or_admin),
    db: Session = Depends(get_db),
):
    asset = Asset(
        name=payload.name,
        description=payload.description,
        location=payload.location,
        asset_type=payload.asset_type,
        owner_id=current_user.id,
        tags=payload.tags,
        # FIX: was `metadata=payload.metadata` — passing `metadata` as a
        # constructor kwarg to a SQLAlchemy declarative model raises
        # `TypeError: 'metadata' is an invalid keyword argument for Asset`
        # (it collides with the reserved Base.metadata attribute), so this
        # endpoint 500'd on every single call — nothing created, ever,
        # which is why the Assets page stayed blank even after "creating"
        # something. The mapped attribute name is extra_metadata.
        extra_metadata=payload.metadata,
        health_status=payload.health_status,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_to_response(asset, db)


@router.get("", response_model=AssetListResponse)
def list_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    asset_type: Optional[str] = None,
    health_status: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import desc, asc
    query = db.query(Asset)

    if search:
        query = query.filter(
            Asset.name.ilike(f"%{search}%") | Asset.description.ilike(f"%{search}%")
        )
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    if health_status:
        query = query.filter(Asset.health_status == health_status)
    if is_active is not None:
        query = query.filter(Asset.is_active == is_active)

    total = query.count()

    sort_col = getattr(Asset, sort_by, Asset.created_at)
    query = query.order_by(desc(sort_col) if sort_order == "desc" else asc(sort_col))
    assets = query.offset((page - 1) * page_size).limit(page_size).all()

    return AssetListResponse(
        items=[_asset_to_response(a, db) for a in assets],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    return _asset_to_response(asset, db)


@router.patch("/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    current_user: User = Depends(require_engineer_or_admin),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")

    # FIX: AssetUpdate has a `metadata: Optional[dict]` field, and this loop
    # used to do a blind `setattr(asset, field, value)` for every field in
    # the payload. `setattr(asset, "metadata", value)` shadows the
    # SQLAlchemy-reserved `Base.metadata` class attribute at the instance
    # level instead of touching the mapped column (which is
    # `extra_metadata`) — so the update silently "succeeded" (no error) but
    # never actually persisted, and every other attribute read afterward
    # risked seeing the wrong object. Remap it explicitly.
    for field, value in payload.model_dump(exclude_none=True).items():
        if field == "metadata":
            asset.extra_metadata = value
        else:
            setattr(asset, field, value)

    db.commit()
    db.refresh(asset)
    return _asset_to_response(asset, db)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: str,
    current_user: User = Depends(require_engineer_or_admin),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    # Unlink documents
    db.query(Document).filter(Document.asset_id == asset_id).update({"asset_id": None})
    db.delete(asset)
    db.commit()


@router.get("/{asset_id}/documents")
def get_asset_documents(
    asset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")

    query = db.query(Document).filter(Document.asset_id == asset_id)
    total = query.count()
    docs = query.offset((page - 1) * page_size).limit(page_size).all()

    from apps.api.schemas.documents import DocumentResponse, DocumentListResponse
    return DocumentListResponse(
        items=docs,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{asset_id}/stats")
def get_asset_stats(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")

    docs = db.query(Document).filter(Document.asset_id == asset_id)
    total_docs = docs.count()
    completed = docs.filter(Document.status == DocumentStatus.completed).count()
    failed = docs.filter(Document.status == DocumentStatus.failed).count()
    processing = docs.filter(Document.status == DocumentStatus.processing).count()
    total_size = db.query(func.sum(Document.file_size)).filter(Document.asset_id == asset_id).scalar() or 0
    total_chunks = db.query(func.sum(Document.chunk_count)).filter(Document.asset_id == asset_id).scalar() or 0

    return {
        "asset_id": asset_id,
        "total_documents": total_docs,
        "completed_documents": completed,
        "failed_documents": failed,
        "processing_documents": processing,
        "total_storage_bytes": total_size,
        "total_chunks": total_chunks,
        "health_status": asset.health_status,
    }