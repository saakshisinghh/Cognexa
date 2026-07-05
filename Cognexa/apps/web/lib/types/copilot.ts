/**
 * apps/web/lib/types/copilot.ts
 *
 * TypeScript types for Phase 4 copilot v2.
 * These mirror the Pydantic schemas in apps/api/schemas/copilot_v2.py
 * and apps/api/schemas/confidence.py exactly — no extra fields, no missing fields.
 */

export type ConfidenceLevel = "high" | "medium" | "low";

export type ConflictSeverity = "minor" | "moderate" | "major";

export interface ConflictFlag {
  topic: string;
  severity: ConflictSeverity;
  chunk_a_id: string;
  chunk_a_excerpt: string;
  chunk_a_document_title: string;
  chunk_b_id: string;
  chunk_b_excerpt: string;
  chunk_b_document_title: string;
  confidence: number;
}

export interface CitationItem {
  chunk_id: string;
  document_id: string;
  document_title: string;
  page_number: number | null;
  excerpt: string;
  sources: string[]; // ["bm25", "vector", "graph"]
  trust_score: number;
}

export interface ConfidencePayload {
  level: ConfidenceLevel;
  score: number;
  explanation: string;
}

/** One turn in the conversation — user or assistant. */
export interface ChatMessage {
  id: string;              // client-generated UUID for React keying
  role: "user" | "assistant";
  content: string;
  citations?: CitationItem[];
  confidence?: ConfidencePayload;
  conflicts?: ConflictFlag[];
  isStreaming?: boolean;   // true while SSE is still delivering tokens
  hasError?: boolean;
  errorMessage?: string;
  timestamp: Date;
}

export interface SessionSummary {
  session_id: string;
  title: string | null;
  message_count: number;
  pinned_asset_tag: string | null;
  last_active_at: string | null;
  is_archived: boolean;
}

export interface SessionDetail {
  session: SessionSummary;
  recent_messages: Array<{ role: "user" | "assistant"; content: string }>;
}

export interface CopilotV2ChatRequest {
  query: string;
  session_id?: string;
  plant_id?: string;
  document_type?: string;
  asset_id?: string;
  stream: boolean;
}

// SSE event shapes — discriminated union on `type`
export type SSEEvent =
  | { type: "token";      content: string }
  | { type: "citations";  citations: CitationItem[] }
  | { type: "confidence"; level: ConfidenceLevel; score: number; explanation: string }
  | { type: "conflicts";  conflicts: ConflictFlag[] }
  | { type: "done";       query_id: string }
  | { type: "error";      message: string; query_id?: string };
