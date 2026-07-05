/**
 * apps/web/lib/graph/api.ts
 *
 * Purpose
 * -------
 * Typed client functions for the Phase 3 Graph API. Wraps the existing
 * authenticated fetch helper from apps/web/lib/api-client.ts (Phase 1 —
 * REUSED, not redefined) so every call automatically carries the JWT.
 *
 * Dependencies
 * ------------
 * - apps/web/lib/api-client.ts (assumed: exports `apiFetch<T>(path, opts)`)
 *
 * This file is NEW.
 */

import { apiFetch } from "@/lib/api-client";

export type NodeLabel =
  | "Asset"
  | "Equipment"
  | "Failure"
  | "FailureMode"
  | "Incident"
  | "Inspection"
  | "Person"
  | "Document"
  | "ComplianceRule"
  | "Site";

export type RelationshipType =
  | "PART_OF"
  | "LOCATED_AT"
  | "CAUSED_BY"
  | "HAS_FAILURE_MODE"
  | "INSPECTED_BY"
  | "REPORTED_IN"
  | "INVOLVES"
  | "AFFECTS"
  | "SIMILAR_TO"
  | "SUBJECT_TO"
  | "AUTHORED_BY";

export interface GraphNode {
  id: string;
  label: NodeLabel | string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: RelationshipType | string;
  properties: Record<string, unknown>;
}

export interface GraphSubgraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center_node_id: string | null;
}

export interface GraphStatsResponse {
  node_counts: Record<string, number>;
  relationship_counts: Record<string, number>;
  total_nodes: number;
  total_relationships: number;
  last_sync_at: string | null;
}

export interface SimilarityResult {
  node_id: string;
  label: string;
  properties: Record<string, unknown>;
  similarity_score: number;
  shared_relationships: number;
}

export interface IncidentPayload {
  title: string;
  description: string;
  asset_id: string;
  document_id?: string | null;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "investigating" | "resolved" | "closed";
  failure_mode_code?: string | null;
  occurred_at: string;
}

export interface IncidentResponse extends IncidentPayload {
  id: string;
  reported_by: string | null;
  graph_sync_status: "pending" | "synced" | "failed";
  graph_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

class GraphApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "GraphApiError";
  }
}

export async function getAssetSubgraph(
  assetId: string,
  depth = 1,
  limit = 100
): Promise<GraphSubgraphResponse> {
  try {
    const res = await apiFetch<GraphSubgraphResponse>(
      `/api/v1/graph/assets/${assetId}/subgraph?depth=${depth}&limit=${limit}`
    );
    return (res as any).data ?? res;
  } catch (err: any) {
    throw new GraphApiError(err?.message ?? "Failed to load asset graph", err?.status ?? 500);
  }
}

export async function expandNode(
  nodeId: string,
  relationshipTypes: RelationshipType[] | null,
  depth = 1,
  limit = 50
): Promise<GraphSubgraphResponse> {
  const res = await apiFetch<GraphSubgraphResponse>(`/api/v1/graph/expand`, {
    method: "POST",
    body: JSON.stringify({
      node_id: nodeId,
      relationship_types: relationshipTypes,
      depth,
      limit,
    }),
  });
  return (res as any).data ?? res;
}

export async function searchGraph(
  query: string,
  labels: NodeLabel[] | null = null,
  limit = 20
): Promise<{ results: GraphNode[]; count: number }> {
  return apiFetch(`/api/v1/graph/search`, {
    method: "POST",
    body: JSON.stringify({ query, labels, limit }),
  });
}

export async function getGraphStats(): Promise<GraphStatsResponse> {
  const res = await apiFetch<GraphStatsResponse>(`/api/v1/graph/stats`);
  return (res as any).data ?? res;
}

export async function getSimilarAssets(
  assetId: string,
  limit = 10
): Promise<SimilarityResult[]> {
  const res = await apiFetch<SimilarityResult[]>(`/api/v1/graph/assets/${assetId}/similar?limit=${limit}`);
  return (res as any).data ?? res;
}

export async function getGraphHealth(): Promise<{ connected: boolean; database: string; error: string | null }> {
  return apiFetch(`/api/v1/graph/health`);
}

// --- Incident CRUD ---
export async function createIncident(payload: IncidentPayload): Promise<IncidentResponse> {
  const res = await apiFetch<IncidentResponse>(`/api/v1/incidents`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return (res as any).data ?? res;
}

export async function listIncidents(
  assetId?: string,
  status?: string
): Promise<IncidentResponse[]> {
  const params = new URLSearchParams();
  if (assetId) params.set("asset_id", assetId);
  if (status) params.set("status", status);
  const res = await apiFetch<IncidentResponse[]>(`/api/v1/incidents?${params.toString()}`);
  return (res as any).data ?? res;
}

export async function updateIncident(
  incidentId: string,
  payload: Partial<IncidentPayload>
): Promise<IncidentResponse> {
  const res = await apiFetch<IncidentResponse>(`/api/v1/incidents/${incidentId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return (res as any).data ?? res;
}

export async function deleteIncident(incidentId: string): Promise<void> {
  await apiFetch(`/api/v1/incidents/${incidentId}`, { method: "DELETE" });
}
