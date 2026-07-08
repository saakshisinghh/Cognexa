/**
 * apps/web/lib/types/knowledge.ts
 *
 * TypeScript types for Phase 6 Knowledge Intelligence features.
 * Mirrors apps/api/schemas/{temporal,gap,loss,disagreement,timeline,persona}.py
 * exactly — no extra fields, no missing fields.
 */

// ─── Temporal Knowledge Intelligence ───────────────────────────────────────

export interface ChunkTemporalInfo {
  chunk_id: string;
  document_id: string;
  trust_score: number;
  valid_from: string | null;
  valid_to: string | null;
  superseded_by_chunk_id: string | null;
  decay_computed_at: string | null;
}

export interface StaleDocumentSummary {
  document_id: string;
  original_filename: string;
  category: string | null;
  is_stale: boolean;
  stale_flagged_at: string | null;
  stale_reason: string | null;
}

// ─── Knowledge Gap Detection ────────────────────────────────────────────────

export interface AssetGapSummary {
  asset_id: string;
  asset_name: string;
  gap_score: number;
  missing_categories: string[];
  present_categories: string[];
  expected_categories: string[];
  incident_count: number;
  incident_penalty_applied: boolean;
  computed_at: string | null;
}

// ─── Knowledge Loss Prediction ──────────────────────────────────────────────

export type RiskLevel = "unknown" | "low" | "medium" | "high" | "critical";

export interface AssetRiskSummary {
  asset_id: string;
  asset_name: string;
  primary_owner_user_id: string | null;
  primary_owner_name: string | null;
  concentration_score: number;
  contributor_count: number;
  retirement_boost_applied: boolean;
  risk_score: number;
  risk_level: RiskLevel;
  mitigation_recommendation: string | null;
  computed_at: string | null;
}

export interface AssetOwnerSummary {
  user_id: string;
  full_name: string;
  document_count: number;
  incident_count: number;
  ownership_score: number;
  is_primary_owner: boolean;
  last_activity_at: string | null;
}

// ─── Expert Disagreement Detection ─────────────────────────────────────────

export type DisagreementSeverity = "minor" | "moderate" | "major";

export interface DisagreementSummary {
  id: string;
  asset_id: string;
  asset_name: string | null;
  topic: string;
  document_a_id: string;
  document_a_title: string;
  document_b_id: string;
  document_b_title: string;
  occurrence_count: number;
  max_severity: DisagreementSeverity;
  sample_excerpt_a: string | null;
  sample_excerpt_b: string | null;
  last_seen_at: string | null;
  is_resolved: boolean;
  resolved_by_user_id: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
}

// ─── Failure Time Machine ───────────────────────────────────────────────────

export type TimelineEventType =
  | "incident" | "document" | "work_order" | "inspection" | "knowledge_superseded";

export interface TimelineEvent {
  event_type: TimelineEventType;
  occurred_at: string;
  title: string;
  description: string | null;
  severity: string | null;
  source_id: string;
  source_url_hint: string | null;
}

export interface AssetTimelineResponse {
  asset_id: string;
  asset_name: string;
  events: TimelineEvent[];
  total: number;
}

export interface ReplayChunkState {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content_excerpt: string;
  trust_score: number;
}

export interface ReplayIncidentState {
  incident_id: string;
  title: string;
  severity: string;
  occurred_at: string;
}

export interface AssetStateSnapshot {
  asset_id: string;
  asset_name: string;
  as_of: string;
  valid_chunks: ReplayChunkState[];
  incidents_to_date: ReplayIncidentState[];
  documents_existing_to_date: number;
  note: string;
}

// ─── AI Shadow Engineer ─────────────────────────────────────────────────────

export interface ExpertKnowledgeEntrySummary {
  id: string;
  author_user_id: string;
  asset_id: string | null;
  title: string;
  content: string;
  tags: string[];
  is_active: boolean;
  created_at: string;
}

export interface ExpertPersonaSummary {
  user_id: string;
  full_name: string;
  entry_count: number;
}
