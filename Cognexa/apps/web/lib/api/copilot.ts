/**
 * apps/web/lib/api/copilot.ts
 *
 * API client functions for Phase 4 copilot v2.
 * All fetch calls go through /api/v1/copilot/v2/* (proxied by Next.js
 * rewrites to the FastAPI backend — same pattern as Phase 1 API calls).
 *
 * BUG FIX (issue #2 / #3 — "Copilot Frontend"/"Copilot Backend" 403s):
 * Every call in this file used a bare `fetch()` with no Authorization
 * header, so the backend's `get_current_user` dependency (which reads a
 * Bearer token via HTTPBearer) always rejected these requests with 403 —
 * this was the actual cause of the reported /copilot/v2/chat,
 * /copilot/v2/sessions, and /copilot/v2/session/{id} 403s, not a
 * permissions/RBAC problem on the backend. Fixed by attaching the same
 * localStorage-held access token that lib/api.ts uses for every other page.
 */

import type {
  SSEEvent,
  CitationItem,
  ConfidencePayload,
  ConflictFlag,
  SessionSummary,
  SessionDetail,
  CopilotV2ChatRequest,
} from "@/lib/types/copilot";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const BASE = `${API_BASE}/api/v1/copilot`;

function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = getAccessToken();
  return {
    ...(extra || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/**
 * Sends a streaming chat request and yields parsed SSEEvent objects
 * via an AsyncGenerator. Callers iterate with `for await (const event of ...)`.
 *
 * Handles:
 *   - Network failure (fetch throws)      → yields { type: "error", message }
 *   - HTTP 4xx/5xx                        → yields { type: "error", message }
 *   - Malformed SSE line                  → skipped (logged to console.warn)
 *   - Stream closed before "done" event   → generator simply returns
 */
export async function* streamChat(
  request: CopilotV2ChatRequest,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  let response: Response;

  try {
    response = await fetch(`${BASE}/v2/chat`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ ...request, stream: true }),
      signal,
    });
  } catch (err: unknown) {
    const message =
      err instanceof Error && err.name === "AbortError"
        ? "Request cancelled."
        : "Network error — could not connect to the server.";
    yield { type: "error", message };
    return;
  }

  if (response.status === 401 || response.status === 403) {
    yield { type: "error", message: "Your session has expired. Please sign in again." };
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
    }
    return;
  }

  if (!response.ok) {
    let detail = `Server error (${response.status})`;
    try {
      const body = await response.json();
      detail = body?.detail ?? detail;
    } catch {
      /* ignore parse error on error response */
    }
    yield { type: "error", message: detail };
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    yield { type: "error", message: "No response stream available." };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? ""; // keep incomplete last line in buffer

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;

      try {
        const event = JSON.parse(raw) as SSEEvent;
        yield event;
        if (event.type === "done" || event.type === "error") return;
      } catch {
        console.warn("[copilot] unparseable SSE line:", raw);
      }
    }
  }
}

/** Non-streaming call — returns the full response JSON (used in tests). */
export async function completeChat(request: CopilotV2ChatRequest) {
  const res = await fetch(`${BASE}/v2/chat`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ ...request, stream: false }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${BASE}/v2/sessions`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load sessions (${res.status})`);
  return res.json();
}

export async function getSessionDetail(sessionId: string): Promise<SessionDetail> {
  const res = await fetch(`${BASE}/v2/sessions/${sessionId}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Session not found (${res.status})`);
  return res.json();
}

export async function pinAsset(
  sessionId: string,
  assetId: string | null,
  assetTag: string | null
) {
  const res = await fetch(`${BASE}/v2/sessions/${sessionId}/pin-asset`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ asset_id: assetId, asset_tag: assetTag }),
  });
  if (!res.ok) throw new Error("Failed to pin asset.");
  return res.json();
}

export async function submitFeedback(queryId: string, feedback: "positive" | "negative") {
  await fetch(`${BASE}/v2/feedback`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ query_id: queryId, feedback }),
  });
}
