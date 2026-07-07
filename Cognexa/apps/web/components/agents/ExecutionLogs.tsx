"use client";

/**
 * apps/web/components/agents/ExecutionLogs.tsx
 *
 * Phase 5 — searchable / filterable raw log view of an execution's
 * steps (complements ToolCallTimeline's visual timeline with a
 * denser, greppable table — useful for engineers debugging a run).
 */
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ExecutionStep } from "@/types";

const STATUS_COLORS: Record<string, string> = {
  completed: "text-green-500",
  failed: "text-red-500",
  retried: "text-amber-500",
  started: "text-primary",
};

export default function ExecutionLogs({ steps }: { steps: ExecutionStep[] }) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const filtered = useMemo(() => {
    return steps.filter((s) => {
      const matchesQuery = query.trim() === "" ||
        s.step.toLowerCase().includes(query.toLowerCase()) ||
        s.detail.toLowerCase().includes(query.toLowerCase());
      const matchesStatus = statusFilter === "all" || s.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [steps, query, statusFilter]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter logs..."
            className="w-full rounded-lg border border-border bg-background pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs"
        >
          <option value="all">All statuses</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="retried">Retried</option>
          <option value="started">Started</option>
        </select>
      </div>

      <div className="rounded-lg border border-border overflow-hidden font-mono text-[11px]">
        <div className="max-h-96 overflow-y-auto divide-y divide-border">
          {filtered.length === 0 && (
            <p className="p-3 text-muted-foreground italic">No matching log entries.</p>
          )}
          {filtered.map((s, idx) => (
            <div key={idx} className="p-2.5 flex items-start gap-2 hover:bg-accent/50">
              <span className="text-muted-foreground shrink-0">
                {s.timestamp ? new Date(s.timestamp).toLocaleTimeString() : "--:--:--"}
              </span>
              <span className={cn("shrink-0 uppercase font-semibold", STATUS_COLORS[s.status] ?? "text-muted-foreground")}>
                {s.status}
              </span>
              <span className="shrink-0 text-foreground">{s.step}</span>
              <span className="text-muted-foreground truncate">{s.detail}</span>
              {typeof s.duration_ms === "number" && (
                <span className="ml-auto shrink-0 text-muted-foreground">{s.duration_ms.toFixed(0)}ms</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
