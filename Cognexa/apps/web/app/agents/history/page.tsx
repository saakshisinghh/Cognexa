"use client";

/**
 * apps/web/app/agents/history/page.tsx
 *
 * Phase 5 — Execution History: searchable, filterable list of past
 * agent runs, each linking to its full detail page.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Search, Clock, CheckCircle2, XCircle, Loader2, Ban } from "lucide-react";
import AppLayout from "@/components/layout/AppLayout";
import { listExecutions } from "@/lib/agents/api";
import { formatRelativeTime, cn } from "@/lib/utils";
import type { AgentExecutionStatus } from "@/types";

const STATUS_META: Record<AgentExecutionStatus, { icon: React.ElementType; color: string }> = {
  completed: { icon: CheckCircle2, color: "text-green-500" },
  failed: { icon: XCircle, color: "text-red-500" },
  running: { icon: Loader2, color: "text-primary" },
  queued: { icon: Clock, color: "text-muted-foreground" },
  cancelled: { icon: Ban, color: "text-amber-500" },
};

export default function AgentHistoryPage() {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["agent-executions", statusFilter, agentFilter],
    queryFn: () => listExecutions({
      status: statusFilter || undefined, agent_key: agentFilter || undefined, limit: 50,
    }),
  });

  const executions = (data?.executions ?? []).filter((e) =>
    query.trim() === "" || e.goal.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <AppLayout>
      <div className="p-8 max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Execution History</h1>
          <p className="text-sm text-muted-foreground mt-1">All past agent runs for your account.</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by goal..."
              className="w-full rounded-lg border border-border bg-background pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
          >
            <option value="">All agents</option>
            <option value="rca_agent">Root Cause Analysis</option>
            <option value="maintenance_agent">Predictive Maintenance</option>
            <option value="compliance_agent">Compliance</option>
            <option value="lessons_agent">Lessons Learned</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="running">Running</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        <div className="rounded-xl border border-border bg-card divide-y divide-border">
          {isLoading && <div className="p-6 text-sm text-muted-foreground">Loading…</div>}
          {!isLoading && executions.length === 0 && (
            <div className="p-6 text-sm text-muted-foreground">No executions found.</div>
          )}
          {executions.map((e) => {
            const meta = STATUS_META[e.status] ?? STATUS_META.queued;
            const StatusIcon = meta.icon;
            return (
              <Link
                key={e.execution_id}
                href={`/agents/executions/${e.execution_id}`}
                className="flex items-center gap-3 p-4 hover:bg-accent/50 transition"
              >
                <StatusIcon className={cn("w-4 h-4 shrink-0", meta.color, e.status === "running" && "animate-spin")} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{e.goal}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {e.agent_key} · {formatRelativeTime(e.created_at)}
                    {e.confidence && ` · confidence: ${e.confidence.level}`}
                  </p>
                </div>
                {e.duration_ms != null && (
                  <span className="text-[11px] text-muted-foreground shrink-0">{(e.duration_ms / 1000).toFixed(1)}s</span>
                )}
              </Link>
            );
          })}
        </div>
      </div>
    </AppLayout>
  );
}
