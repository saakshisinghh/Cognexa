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
  // Phase 6: Temporal Knowledge Intelligence
  is_stale?: boolean;
  stale_flagged_at?: string | null;
  stale_reason?: string | null;
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

// ─── Phase 2: Audit ───────────────────────────────────────────────────────────

export type AuditAction =
  | "login" | "logout" | "login_failed" | "upload" | "delete" | "rename"
  | "update" | "search" | "chat_query" | "download" | "role_change"
  | "asset_update" | "settings_change" | "api_error" | "auth_failure"
  | "reprocess" | "retry_task" | "cancel_task";

export type AuditStatus = "success" | "failure" | "denied";

export interface AuditLog {
  id: string;
  timestamp: string;
  user_id: string | null;
  user_email: string | null;
  role: string | null;
  ip_address: string | null;
  user_agent: string | null;
  resource: string | null;
  action: AuditAction;
  status: AuditStatus;
  old_value: unknown;
  new_value: unknown;
  duration_ms: number | null;
  correlation_id: string | null;
  detail: string | null;
}

export interface AuditFilters {
  action?: string;
  status?: string;
  user_id?: string;
  resource?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
}

// ─── Phase 2: Processing Jobs ─────────────────────────────────────────────────

export type JobStatus = "pending" | "queued" | "processing" | "completed" | "failed" | "cancelled";
export type JobStep =
  | "created" | "ocr" | "entity_extraction" | "chunking"
  | "embedding" | "vector_storage" | "finalizing" | "done";

export interface TaskExecution {
  id: string;
  celery_task_id: string;
  task_name: string;
  queue: string;
  state: string;
  attempt: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
}

export interface ProcessingJob {
  id: string;
  document_id: string;
  status: JobStatus;
  current_step: JobStep;
  progress_percent: number;
  celery_task_id: string | null;
  retry_count: number;
  max_retries: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProcessingJobDetail extends ProcessingJob {
  tasks: TaskExecution[];
}

export interface QueueMetrics {
  queue_name: string;
  pending: number;
  active: number;
  scheduled: number;
  reserved: number;
}

export interface WorkerHealth {
  worker_name: string;
  status: string;
  active_tasks: number;
  processed_tasks: number;
  concurrency: number;
  last_heartbeat: string | null;
}

export interface ProcessingStats {
  running_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  retry_queue: number;
  avg_processing_time_seconds: number;
  redis: { status: string; latency_ms?: number; used_memory_human?: string };
  queues: QueueMetrics[];
  workers: WorkerHealth[];
}

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

// ─── Phase 5: Agents / Multi-Agent Workflow ────────────────────────────────
// FIX: this whole section was dropped when the Phase 6 (Knowledge
// Intelligence) fields above were merged in — apps/api/schemas/agents.py
// and every apps/web/components/agents/*.tsx file still expect these,
// which is why the build failed with "Module '@/types' has no exported
// member 'AgentDescriptor'" etc. Field names/shapes mirror
// apps/api/schemas/agents.py and apps/api/agents/state.py exactly.

export type AgentExecutionMode = "single" | "sequential" | "parallel" | "supervisor";

export type AgentExecutionStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface AgentDescriptor {
  agent_key: string;
  name: string;
  description: string;
  version: string;
  capabilities: string[];
  is_enabled: boolean;
  health_status: string;
}

export interface AgentConfidence {
  level: "high" | "medium" | "low" | string;
  raw_score: number;
  factors: {
    avg_trust_score?: number;
    has_conflict?: boolean;
    conflict_penalty_applied?: number;
    [key: string]: unknown;
  };
  explanation: string;
}

export interface ExecutionStep {
  step: string;
  status: string;
  detail: string;
  timestamp: string;
  duration_ms?: number | null;
}

export interface ExecutionSummary {
  execution_id: string;
  agent_key: string;
  goal: string;
  status: AgentExecutionStatus;
  mode: AgentExecutionMode;
  workflow_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  confidence?: AgentConfidence | null;
}

export interface ExecutionDetail extends ExecutionSummary {
  plan?: Record<string, unknown> | null;
  answer?: string | null;
  structured_output?: Record<string, unknown> | null;
  sources: Record<string, unknown>[];
  errors: Record<string, unknown>[];
  steps: ExecutionStep[];
}

export interface WorkflowStep {
  agent_key: string;
  execution_id: string;
  status: AgentExecutionStatus;
  answer?: string | null;
  confidence?: AgentConfidence | null;
}

export interface WorkflowConflict {
  agents: string[];
  issue: string;
  [key: string]: unknown;
}

export interface WorkflowDetail {
  workflow_id: string;
  goal: string;
  mode: AgentExecutionMode;
  status: AgentExecutionStatus;
  agent_keys: string[];
  steps: WorkflowStep[];
  final_answer?: string | null;
  conflicts: WorkflowConflict[];
  created_at: string;
  completed_at?: string | null;
}

export type AgentStreamEvent =
  | { type: "node"; node: string; output: Record<string, any> }
  | { type: "done"; execution_id: string; status: string }
  | { type: "error"; message: string };
