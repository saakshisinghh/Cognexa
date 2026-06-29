from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


# ─── Asset Schemas ───────────────────────────────────────────────────────────

class AssetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    asset_type: Optional[str] = None
    tags: List[str] = []
    metadata: dict = {}
    health_status: str = "unknown"


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    asset_type: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None
    health_status: Optional[str] = None
    is_active: Optional[bool] = None


class AssetResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    asset_type: Optional[str] = None
    owner_id: Optional[str] = None
    tags: List[str] = []
    metadata: dict = {}
    health_status: str
    is_active: bool
    document_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    items: List[AssetResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ─── Search Schemas ───────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    asset_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    min_score: float = 0.0


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    asset_id: Optional[str] = None
    asset_name: Optional[str] = None
    text: str
    score: float
    page_number: Optional[int] = None
    chunk_index: int
    highlight: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total: int
    took_ms: float


# ─── Copilot Schemas ──────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: Optional[str] = None
    document_id: Optional[str] = None


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    sources: List[dict] = []
    confidence: Optional[float] = None
    tokens_used: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: str
    title: Optional[str] = None
    user_id: str
    document_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    items: List[ConversationResponse]
    total: int


# ─── Dashboard Schemas ────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_documents: int
    total_assets: int
    total_users: int
    total_conversations: int
    documents_processing: int
    documents_completed: int
    documents_failed: int
    storage_used_bytes: int
    recent_uploads: List[Any] = []
    recent_searches: List[Any] = []
    recent_conversations: List[Any] = []


# ─── Health Schema ────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict
