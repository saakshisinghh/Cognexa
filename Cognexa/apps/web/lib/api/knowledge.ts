/**
 * apps/web/lib/api/knowledge.ts
 *
 * API client for Phase 6: Temporal Knowledge Intelligence, Knowledge Gap
 * Detection, Knowledge Loss Prediction, Expert Disagreement Detection.
 * Follows the same `import api from "@/lib/api"` axios convention as
 * lib/api/copilot.ts.
 */

import api from "@/lib/api";
import type {
  StaleDocumentSummary,
  AssetGapSummary,
  AssetRiskSummary,
  AssetOwnerSummary,
  DisagreementSummary,
} from "@/lib/types/knowledge";

// ─── Temporal ────────────────────────────────────────────────────────────

export async function getStaleDocuments(): Promise<StaleDocumentSummary[]> {
  const res = await api.get("/temporal/documents/stale");
  return res.data.documents;
}

export async function triggerTemporalRecompute(task: string = "trust_scores") {
  const res = await api.post(`/temporal/recompute?task=${task}`);
  return res.data;
}

// ─── Gap Detection ───────────────────────────────────────────────────────

export async function getAssetGaps(minGapScore: number = 0): Promise<AssetGapSummary[]> {
  const res = await api.get("/gap/assets", { params: { min_gap_score: minGapScore } });
  return res.data.assets;
}

export async function getAssetGap(assetId: string): Promise<AssetGapSummary> {
  const res = await api.get(`/gap/assets/${assetId}`);
  return res.data;
}

export async function triggerGapRecompute() {
  const res = await api.post("/gap/recompute");
  return res.data;
}

// ─── Loss Prediction ─────────────────────────────────────────────────────

export async function getAssetRisks(minRiskScore: number = 0): Promise<AssetRiskSummary[]> {
  const res = await api.get("/loss/assets", { params: { min_risk_score: minRiskScore } });
  return res.data.assets;
}

export async function getAssetOwners(assetId: string): Promise<AssetOwnerSummary[]> {
  const res = await api.get(`/loss/assets/${assetId}/owners`);
  return res.data.owners;
}

export async function setRetirementFlag(userId: string, isRetirementRisk: boolean, notes?: string) {
  const res = await api.patch(`/loss/users/${userId}/retirement-flag`, {
    is_retirement_risk: isRetirementRisk,
    notes: notes ?? null,
  });
  return res.data;
}

export async function triggerLossRecompute() {
  const res = await api.post("/loss/recompute");
  return res.data;
}

// ─── Expert Disagreement Detection ──────────────────────────────────────

export async function getDisagreements(includeResolved: boolean = false): Promise<DisagreementSummary[]> {
  const res = await api.get("/disagreements", { params: { include_resolved: includeResolved } });
  return res.data.disagreements;
}

export async function getAssetDisagreements(assetId: string, includeResolved: boolean = false): Promise<DisagreementSummary[]> {
  const res = await api.get(`/disagreements/assets/${assetId}`, { params: { include_resolved: includeResolved } });
  return res.data.disagreements;
}

export async function resolveDisagreement(id: string, notes?: string) {
  const res = await api.patch(`/disagreements/${id}/resolve`, { notes: notes ?? null });
  return res.data;
}

export async function triggerDisagreementRecompute() {
  const res = await api.post("/disagreements/recompute");
  return res.data;
}
