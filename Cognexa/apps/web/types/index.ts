// ─── Auth ─────────────────────────────────────────────────────────────────────

export type UserRole = "admin" | "engineer" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ─── Documents ────────────────────────────────────────────────────────────────

export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface Document {
  id: string;
  filename: string;
  original_filename: string;
  file_size: number;
  mime_type: string;
  version: number;
  status: DocumentStatus;
  ocr_status: string;
  embedding_status: string;
  chunk_count: number;
  entity_count: number;
  page_count: number;
  language: string | null;
  category: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
  owner_id: string | null;
  asset_id: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends Document {
  chunks: Chunk[];
  extracted_text: string | null;
}

export interface Chunk {
  id: string;
  document_id: string;
  chunk_index: number;
  text: string;
  page_number: number | null;
  token_count: number;
  metadata: Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ─── Assets ───────────────────────────────────────────────────────────────────

export interface Asset {
  id: string;
  name: string;
  description: string | null;
  location: string | null;
  asset_type: string | null;
  owner_id: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
  health_status: string;
  is_active: boolean;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface AssetStats {
  asset_id: string;
  total_documents: number;
  completed_documents: number;
  failed_documents: number;
  processing_documents: number;
  total_storage_bytes: number;
  total_chunks: number;
  health_status: string;
}

// ─── Search ───────────────────────────────────────────────────────────────────

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_name: string;
  asset_id: string | null;
  asset_name: string | null;
  text: string;
  score: number;
  page_number: number | null;
  chunk_index: number;
  highlight: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
  took_ms: number;
}

// ─── Copilot ──────────────────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  title: string | null;
  user_id: string;
  document_id: string | null;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  sources: MessageSource[];
  confidence: number | null;
  tokens_used: number;
  created_at: string;
}

export interface MessageSource {
  document_id: string;
  page_number: number | null;
  source: string;
  score: number;
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export interface DashboardStats {
  total_documents: number;
  total_assets: number;
  total_users: number;
  total_conversations: number;
  documents_processing: number;
  documents_completed: number;
  documents_failed: number;
  storage_used_bytes: number;
  recent_uploads: Array<{
    id: string;
    filename: string;
    status: DocumentStatus;
    created_at: string;
  }>;
  recent_conversations: Array<{
    id: string;
    title: string | null;
    updated_at: string;
  }>;
}
