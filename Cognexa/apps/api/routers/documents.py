"""
Documents Router — Upload, OCR, embed, CRUD, search, bulk ops.
"""
from __future__ import annotations
import io
import logging
import math
import mimetypes
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, BackgroundTasks
from sqlalchemy.orm import Session
from minio import Minio
from minio.error import S3Error

from apps.api.config import settings
from apps.api.db import get_db
from apps.api.models import Document, DocumentStatus, User, Chunk
from apps.api.routers.auth import get_current_user, require_engineer_or_admin
from apps.api.schemas.documents import (
    DocumentResponse, DocumentListResponse, DocumentUpdate,
    DocumentDetailResponse, UploadResponse, ChunkResponse
)
from apps.api.weaviate_client import get_weaviate_client
from apps.api.services import ocr as ocr_svc
from apps.api.services import chunker as chunker_svc
from apps.api.services import extractor as extractor_svc
from apps.api.services import embedder as embedder_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_MIMES = {
    "application/pdf",
    "image/jpeg", "image/png", "image/tiff", "image/webp",
    "text/plain", "text/markdown", "text/csv",
}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


# ─── MinIO Client ─────────────────────────────────────────────────────────────

def get_minio_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket(client: Minio) -> None:
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)


# ─── Background Processing ────────────────────────────────────────────────────

def _process_document(document_id: str, file_bytes: bytes, mime_type: str, filename: str):
    """Full OCR → chunk → embed pipeline run in background."""
    from apps.api.db import SessionLocal
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return

        doc.status = DocumentStatus.processing
        doc.ocr_status = "processing"
        db.commit()

        # 1. OCR
        try:
            result = ocr_svc.extract_text_and_metadata(file_bytes, mime_type, filename)
            doc.extracted_text = result["text"]
            doc.page_count = result["page_count"]
            doc.language = result["language"]
            doc.metadata = {**doc.metadata, **result["metadata"], "ocr_engine": result["ocr_engine"]}
            doc.ocr_status = "completed"
            db.commit()
        except Exception as e:
            logger.error(f"OCR failed for {document_id}: {e}")
            doc.ocr_status = "failed"
            doc.status = DocumentStatus.failed
            doc.error_message = f"OCR failed: {str(e)}"
            db.commit()
            return

        # 2. Entity extraction
        try:
            entities = extractor_svc.extract_entities(doc.extracted_text or "")
            doc.entity_count = len(entities)
            doc.metadata = {**doc.metadata, "entities": entities[:50]}  # store top 50
            db.commit()
        except Exception as e:
            logger.warning(f"Entity extraction failed for {document_id}: {e}")

        # 3. Chunking
        doc.embedding_status = "processing"
        db.commit()
        try:
            chunks = chunker_svc.split_text(
                text=doc.extracted_text or "",
                document_id=document_id,
                source=doc.original_filename,
            )

            # Store chunks in DB
            db_chunks = []
            for ch in chunks:
                db_chunk = Chunk(
                    document_id=document_id,
                    chunk_index=ch.chunk_index,
                    text=ch.text,
                    page_number=ch.page_number,
                    token_count=ch.token_count,
                    metadata=ch.metadata,
                )
                db_chunks.append(db_chunk)
            db.bulk_save_objects(db_chunks)
            doc.chunk_count = len(chunks)
            db.commit()

            # Refresh to get IDs
            db.refresh(doc)
            db_chunks_saved = db.query(Chunk).filter(Chunk.document_id == document_id).all()

        except Exception as e:
            logger.error(f"Chunking failed for {document_id}: {e}")
            doc.embedding_status = "failed"
            doc.status = DocumentStatus.failed
            doc.error_message = f"Chunking failed: {str(e)}"
            db.commit()
            return

        # 4. Embedding → Weaviate
        try:
            wv_client = get_weaviate_client()
            wv_ids = embedder_svc.embed_and_store_chunks(
                chunks=chunks,
                document_id=document_id,
                asset_id=doc.asset_id,
                source=doc.original_filename,
                weaviate_client=wv_client,
            )
            # Save weaviate IDs back
            for db_chunk, wv_id in zip(db_chunks_saved, wv_ids):
                db_chunk.weaviate_id = wv_id
            db.commit()

            doc.embedding_status = "completed"
            doc.status = DocumentStatus.completed
            db.commit()
            logger.info(f"Document {document_id} processing complete")

        except Exception as e:
            logger.error(f"Embedding failed for {document_id}: {e}")
            doc.embedding_status = "failed"
            doc.status = DocumentStatus.failed
            doc.error_message = f"Embedding failed: {str(e)}"
            db.commit()

    except Exception as e:
        logger.error(f"Document processing pipeline error for {document_id}: {e}")
        db.rollback()
    finally:
        db.close()


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    asset_id: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    current_user: User = Depends(require_engineer_or_admin),
    db: Session = Depends(get_db),
):
    # Validate MIME
    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if mime_type not in ALLOWED_MIMES:
        raise HTTPException(400, f"Unsupported file type: {mime_type}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 100MB)")
    if len(file_bytes) == 0:
        raise HTTPException(400, "File is empty")

    # Parse tags
    tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    # Upload to MinIO
    minio = get_minio_client()
    ensure_bucket(minio)

    import uuid
    doc_id = str(uuid.uuid4())
    safe_filename = f"{doc_id}/{file.filename}"

    minio.put_object(
        settings.MINIO_BUCKET,
        safe_filename,
        io.BytesIO(file_bytes),
        length=len(file_bytes),
        content_type=mime_type,
    )

    # Create DB record
    doc = Document(
        id=doc_id,
        filename=safe_filename,
        original_filename=file.filename or "unknown",
        file_path=f"s3://{settings.MINIO_BUCKET}/{safe_filename}",
        file_size=len(file_bytes),
        mime_type=mime_type,
        owner_id=current_user.id,
        asset_id=asset_id,
        category=category,
        tags=tags_list,
        status=DocumentStatus.pending,
    )
    db.add(doc)
    db.commit()

    # Queue background processing
    background_tasks.add_task(
        _process_document, doc_id, file_bytes, mime_type, file.filename or "unknown"
    )

    return UploadResponse(
        document_id=doc_id,
        filename=file.filename or "unknown",
        status="processing",
        message="Document uploaded successfully. Processing started.",
    )


@router.post("/bulk-upload", status_code=201)
async def bulk_upload(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    asset_id: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    current_user: User = Depends(require_engineer_or_admin),
    db: Session = Depends(get_db),
):
    if len(files) > 20:
        raise HTTPException(400, "Maximum 20 files per bulk upload")

    results = []
    for file in files:
        mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
        if mime_type not in ALLOWED_MIMES:
            results.append({"filename": file.filename, "status": "rejected", "reason": "Unsupported type"})
            continue

        file_bytes = await file.read()
        if len(file_bytes) > MAX_FILE_SIZE or len(file_bytes) == 0:
            results.append({"filename": file.filename, "status": "rejected", "reason": "Invalid size"})
            continue

        import uuid
        doc_id = str(uuid.uuid4())
        safe_filename = f"{doc_id}/{file.filename}"

        minio = get_minio_client()
        ensure_bucket(minio)
        minio.put_object(
            settings.MINIO_BUCKET, safe_filename, io.BytesIO(file_bytes),
            length=len(file_bytes), content_type=mime_type,
        )

        doc = Document(
            id=doc_id,
            filename=safe_filename,
            original_filename=file.filename or "unknown",
            file_path=f"s3://{settings.MINIO_BUCKET}/{safe_filename}",
            file_size=len(file_bytes),
            mime_type=mime_type,
            owner_id=current_user.id,
            asset_id=asset_id,
            category=category,
            tags=[],
        )
        db.add(doc)
        db.flush()
        background_tasks.add_task(_process_document, doc_id, file_bytes, mime_type, file.filename or "unknown")
        results.append({"filename": file.filename, "document_id": doc_id, "status": "processing"})

    db.commit()
    return {"uploaded": len([r for r in results if r["status"] == "processing"]), "results": results}


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    asset_id: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import desc, asc
    query = db.query(Document)

    if status:
        query = query.filter(Document.status == status)
    if asset_id:
        query = query.filter(Document.asset_id == asset_id)
    if category:
        query = query.filter(Document.category == category)
    if search:
        query = query.filter(Document.original_filename.ilike(f"%{search}%"))

    total = query.count()

    sort_col = getattr(Document, sort_by, Document.created_at)
    if sort_order == "desc":
        query = query.order_by(desc(sort_col))
    else:
        query = query.order_by(asc(sort_col))

    docs = query.offset((page - 1) * page_size).limit(page_size).all()

    return DocumentListResponse(
        items=docs,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: str,
    payload: DocumentUpdate,
    current_user: User = Depends(require_engineer_or_admin),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    if payload.original_filename is not None:
        doc.original_filename = payload.original_filename
    if payload.category is not None:
        doc.category = payload.category
    if payload.tags is not None:
        doc.tags = payload.tags
    if payload.metadata is not None:
        doc.metadata = {**doc.metadata, **payload.metadata}
    if payload.asset_id is not None:
        doc.asset_id = payload.asset_id

    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    current_user: User = Depends(require_engineer_or_admin),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Delete from Weaviate
    try:
        wv_client = get_weaviate_client()
        embedder_svc.delete_document_embeddings(document_id, wv_client)
    except Exception as e:
        logger.warning(f"Weaviate cleanup failed for {document_id}: {e}")

    # Delete from MinIO
    try:
        minio = get_minio_client()
        minio.remove_object(settings.MINIO_BUCKET, doc.filename)
    except Exception as e:
        logger.warning(f"MinIO cleanup failed for {document_id}: {e}")

    db.delete(doc)
    db.commit()


@router.post("/{document_id}/reprocess", response_model=UploadResponse)
def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_engineer_or_admin),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Fetch from MinIO
    try:
        minio = get_minio_client()
        obj = minio.get_object(settings.MINIO_BUCKET, doc.filename)
        file_bytes = obj.read()
    except Exception as e:
        raise HTTPException(500, f"Could not retrieve file from storage: {e}")

    # Reset status
    doc.status = DocumentStatus.pending
    doc.ocr_status = "pending"
    doc.embedding_status = "pending"
    doc.chunk_count = 0
    doc.entity_count = 0
    doc.error_message = None

    # Delete old chunks & embeddings
    db.query(Chunk).filter(Chunk.document_id == document_id).delete()
    try:
        wv_client = get_weaviate_client()
        embedder_svc.delete_document_embeddings(document_id, wv_client)
    except Exception:
        pass

    doc.version += 1
    db.commit()

    background_tasks.add_task(
        _process_document, document_id, file_bytes, doc.mime_type, doc.original_filename
    )

    return UploadResponse(
        document_id=document_id,
        filename=doc.original_filename,
        status="processing",
        message="Reprocessing started.",
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    try:
        minio = get_minio_client()
        obj = minio.get_object(settings.MINIO_BUCKET, doc.filename)
        return StreamingResponse(
            obj,
            media_type=doc.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{doc.original_filename}"'},
        )
    except S3Error as e:
        raise HTTPException(404, f"File not found in storage: {e}")


@router.get("/{document_id}/chunks", response_model=List[ChunkResponse])
def get_document_chunks(
    document_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return chunks
