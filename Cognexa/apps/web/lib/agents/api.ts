/**
 * apps/web/lib/agents/api.ts
 *
 * Phase 5 — Agent Console API layer.
 *
 * Reuses the existing axios instance (lib/api.ts) for all standard
 * request/response endpoints, matching the convention used by
 * app/assets, app/documents, etc. Streaming (`runAgentStream`) uses the
 * native fetch + ReadableStream API directly, since axios does not
 * expose incrementally-readable response bodies in the browser — the
 * same reason apps/api/routers/copilot.py's stream endpoint is consumed
 * with raw fetch on the frontend.
 */
import api from "@/lib/api";
import type {
  AgentDescriptor, ExecutionDetail, ExecutionSummary, WorkflowDetail,
  AgentStreamEvent, AgentExecutionMode,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function listAgents(): Promise<AgentDescriptor[]> {
  const res = await api.get<{ agents: AgentDescriptor[] }>("/agents");
  return res.data.agents;
}

export async function getAgent(agentKey: string): Promise<AgentDescriptor> {
  const res = await api.get<AgentDescriptor>(`/agents/${agentKey}`);
  return res.data;
}

export async function setAgentEnabled(agentKey: string, enabled: boolean): Promise<AgentDescriptor> {
  const res = await api.patch<AgentDescriptor>(`/agents/${agentKey}`, { is_enabled: enabled });
  return res.data;
}

export async function checkAgentHealth(agentKey: string) {
  const res = await api.get(`/agents/${agentKey}/health`);
  return res.data;
}

export async function runAgent(
  agentKey: string, goal: string, context: Record<string, unknown> = {},
): Promise<ExecutionDetail> {
  const res = await api.post<ExecutionDetail>(`/agents/${agentKey}/run`, { goal, context, stream: false });
  return res.data;
}

export async function cancelExecution(agentKey: string, executionId: string) {
  const res = await api.post(`/agents/${agentKey}/cancel/${executionId}`);
  return res.data;
}

export async function listExecutions(params: {
  agent_key?: string; status?: string; limit?: number; offset?: number;
} = {}): Promise<{ executions: ExecutionSummary[]; total: number }> {
  const res = await api.get("/agents/executions", { params });
  return res.data;
}

export async function getExecution(executionId: string): Promise<ExecutionDetail> {
  const res = await api.get<ExecutionDetail>(`/agents/executions/${executionId}`);
  return res.data;
}

export async function runWorkflow(
  goal: string, agentKeys: string[], mode: AgentExecutionMode = "sequential",
  context: Record<string, unknown> = {},
): Promise<WorkflowDetail> {
  const res = await api.post<WorkflowDetail>("/agents/workflows", { goal, agent_keys: agentKeys, mode, context });
  return res.data;
}

export async function getWorkflow(workflowId: string): Promise<WorkflowDetail> {
  const res = await api.get<WorkflowDetail>(`/agents/workflows/${workflowId}`);
  return res.data;
}

/**
 * Streams an agent run over SSE, invoking `onEvent` for each parsed event.
 * Returns a cancel() function the caller can invoke to abort the stream
 * (used by the "Cancel" button in AgentChat while a run is in flight).
 */
export function runAgentStream(
  agentKey: string,
  goal: string,
  context: Record<string, unknown>,
  onEvent: (event: AgentStreamEvent) => void,
  onError: (message: string) => void,
): { cancel: () => void } {
  const controller = new AbortController();

  (async () => {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
      const response = await fetch(`${API_BASE}/api/v1/agents/${agentKey}/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ goal, context, stream: true }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        onError(`Request failed (${response.status})`);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.replace(/^data:\s*/, "").trim();
          if (!trimmed) continue;
          try {
            onEvent(JSON.parse(trimmed) as AgentStreamEvent);
          } catch {
            // ignore unparseable keep-alive lines
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError((err as Error).message || "Stream failed");
      }
    }
  })();

  return { cancel: () => controller.abort() };
}
