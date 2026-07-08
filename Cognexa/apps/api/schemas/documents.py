from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from datetime import datetime
from apps.api.models import DocumentStatus


class DocumentResponse(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    version: int
    status: DocumentStatus
    ocr_status: str
    embedding_status: str
    chunk_count: int
    entity_count: int
    page_count: int
    language: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = []
    metadata: dict = {}
    owner_id: Optional[str] = None
    asset_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Phase 6: Temporal Knowledge Intelligence — set by the nightly
    # flag_stale_documents_task; new fields, existing clients that don't
    # read them are unaffected.
    is_stale: bool = False
    stale_flagged_at: Optional[datetime] = None
    stale_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DocumentUpdate(BaseModel):
    original_filename: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None
    asset_id: Optional[str] = None


class ChunkResponse(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    text: str
    page_number: Optional[int] = None
    token_count: int
    metadata: dict = {}

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    chunks: List[ChunkResponse] = []
    extracted_text: Optional[str] = None


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    message: str
    job_id: Optional[str] = None
