/**
 * apps/web/lib/api/timeline.ts
 *
 * API client for Phase 6: Failure Time Machine.
 */

import api from "@/lib/api";
import type { AssetTimelineResponse, AssetStateSnapshot } from "@/lib/types/knowledge";

export async function getAssetTimeline(
  assetId: string,
  startDate?: string,
  endDate?: string
): Promise<AssetTimelineResponse> {
  const res = await api.get(`/timeline/assets/${assetId}`, {
    params: { start_date: startDate, end_date: endDate },
  });
  return res.data;
}

export async function replayAssetState(assetId: string, asOf: string): Promise<AssetStateSnapshot> {
  const res = await api.get(`/timeline/assets/${assetId}/replay`, { params: { as_of: asOf } });
  return res.data;
}
