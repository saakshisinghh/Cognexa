/**
 * apps/web/lib/api/persona.ts
 *
 * API client for Phase 6: AI Shadow Engineer.
 */

import api from "@/lib/api";
import type { ExpertKnowledgeEntrySummary, ExpertPersonaSummary } from "@/lib/types/knowledge";

export async function captureEntry(
  title: string,
  content: string,
  assetId?: string,
  tags?: string[]
): Promise<ExpertKnowledgeEntrySummary> {
  const res = await api.post("/persona/entries", {
    title,
    content,
    asset_id: assetId ?? null,
    tags: tags ?? [],
  });
  return res.data;
}

export async function listEntries(authorUserId?: string, assetId?: string): Promise<ExpertKnowledgeEntrySummary[]> {
  const res = await api.get("/persona/entries", {
    params: { author_user_id: authorUserId, asset_id: assetId },
  });
  return res.data.entries;
}

export async function deactivateEntry(entryId: string): Promise<void> {
  await api.delete(`/persona/entries/${entryId}`);
}

export async function listExperts(): Promise<ExpertPersonaSummary[]> {
  const res = await api.get("/persona/experts");
  return res.data.experts;
}
