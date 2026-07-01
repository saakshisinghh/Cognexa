"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import { cn, formatDate } from "@/lib/utils";
import type { ProcessingJob, ProcessingStats } from "@/types";
import {
  Activity, RefreshCw, XCircle, CheckCircle2, Loader2, Clock,
  AlertCircle, Server, Database, Gauge,
} from "lucide-react";

interface JobListResponse {
  items: ProcessingJob[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle2; color: string; bg: string }> = {
  completed: { icon: CheckCircle2, color: "text-green-500", bg: "bg-green-500/10" },
  processing: { icon: Loader2, color: "text-yellow-500", bg: "bg-yellow-500/10" },
  queued: { icon: Clock, color: "text-blue-500", bg: "bg-blue-500/10" },
  pending: { icon: Clock, color: "text-muted-foreground", bg: "bg-muted" },
  failed: { icon: AlertCircle, color: "text-red-500", bg: "bg-red-500/10" },
  cancelled: { icon: XCircle, color: "text-muted-foreground", bg: "bg-muted" },
};

function StatCard({ label, value, icon: Icon }: { label: string; value: React.ReactNode; icon: typeof Activity }) {
  return (
    <div className="p-4 rounded-xl border border-border bg-card flex items-center gap-3">
      <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
        <Icon className="w-4 h-4 text-primary" />
      </div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-lg font-bold leading-tight">{value}</p>
      </div>
    </div>
  );
}

export default function ProcessingDashboardPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");

  const { data: stats } = useQuery<ProcessingStats>({
    queryKey: ["processing-stats"],
    queryFn: () => api.get("/jobs/stats/overview").then((r) => r.data),
    refetchInterval: 10_000,
  });

  const { data: jobs, isLoading } = useQuery<JobListResponse>({
    queryKey: ["jobs", statusFilter],
    queryFn: () => api.get("/jobs", { params: { status: statusFilter || undefined, page_size: 50 } }).then((r) => r.data),
    refetchInterval: 5_000,
  });

  const retryMutation = useMutation({
    mutationFn: (id: string) => api.post(`/jobs/${id}/retry`),
    onSuccess: () => {
      toast.success("Job re-queued");
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Retry failed"),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.post(`/jobs/${id}/cancel`),
    onSuccess: () => {
      toast.success("Job cancelled");
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Cancel failed"),
  });

  return (
    <AppLayout>
      <div className="p-8 max-w-7xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <Activity className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Processing Dashboard</h1>
            <p className="text-sm text-muted-foreground">Async document pipeline — jobs, queues & workers</p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Running" value={stats?.running_jobs ?? "—"} icon={Loader2} />
          <StatCard label="Completed" value={stats?.completed_jobs ?? "—"} icon={CheckCircle2} />
          <StatCard label="Failed" value={stats?.failed_jobs ?? "—"} icon={AlertCircle} />
          <StatCard
            label="Avg. Time"
            value={stats ? `${stats.avg_processing_time_seconds.toFixed(1)}s` : "—"}
            icon={Gauge}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 rounded-xl border border-border bg-card">
            <p className="text-sm font-medium mb-3 flex items-center gap-2">
              <Database className="w-4 h-4 text-muted-foreground" /> Redis
            </p>
            <div className="flex items-center justify-between text-sm">
              <span className={cn(stats?.redis.status === "ok" ? "text-green-500" : "text-red-500")}>
                {stats?.redis.status === "ok" ? "Connected" : "Unreachable"}
              </span>
              <span className="text-muted-foreground">
                {stats?.redis.latency_ms != null ? `${stats.redis.latency_ms}ms latency` : ""}
              </span>
            </div>
          </div>
          <div className="p-4 rounded-xl border border-border bg-card">
            <p className="text-sm font-medium mb-3 flex items-center gap-2">
              <Server className="w-4 h-4 text-muted-foreground" /> Workers
            </p>
            {stats?.workers.length ? (
              <div className="space-y-1.5">
                {stats.workers.map((w) => (
                  <div key={w.worker_name} className="flex items-center justify-between text-sm">
                    <span className="truncate">{w.worker_name}</span>
                    <span className={cn(w.status === "online" ? "text-green-500" : "text-muted-foreground")}>
                      {w.status} · {w.active_tasks} active
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No worker heartbeats recorded yet.</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {["", "queued", "processing", "completed", "failed", "cancelled"].map((s) => (
            <button
              key={s || "all"}
              onClick={() => setStatusFilter(s)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded-full border transition",
                statusFilter === s
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-accent"
              )}
            >
              {s || "All"}
            </button>
          ))}
        </div>

        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-3 font-medium">Job</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Step</th>
                <th className="px-4 py-3 font-medium">Progress</th>
                <th className="px-4 py-3 font-medium">Started</th>
                <th className="px-4 py-3 font-medium">Duration</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">Loading…</td></tr>
              ) : jobs?.items.length ? (
                jobs.items.map((job) => {
                  const cfg = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
                  return (
                    <tr key={job.id} className="border-t border-border hover:bg-accent/30">
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{job.id.slice(0, 8)}</td>
                      <td className="px-4 py-3">
                        <span className={cn("flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium w-fit", cfg.color, cfg.bg)}>
                          <cfg.icon className={cn("w-3 h-3", job.status === "processing" && "animate-spin")} />
                          {job.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground capitalize">{job.current_step.replace(/_/g, " ")}</td>
                      <td className="px-4 py-3">
                        <div className="w-28 h-1.5 rounded-full bg-muted overflow-hidden">
                          <div className="h-full bg-primary transition-all" style={{ width: `${job.progress_percent}%` }} />
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                        {job.started_at ? formatDate(job.started_at) : "—"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {job.duration_seconds != null ? `${job.duration_seconds.toFixed(1)}s` : "—"}
                      </td>
                      <td className="px-4 py-3 text-right space-x-2">
                        {job.status === "failed" && job.retry_count < job.max_retries && (
                          <button
                            onClick={() => retryMutation.mutate(job.id)}
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            <RefreshCw className="w-3 h-3" /> Retry
                          </button>
                        )}
                        {["queued", "processing", "pending"].includes(job.status) && (
                          <button
                            onClick={() => cancelMutation.mutate(job.id)}
                            className="inline-flex items-center gap-1 text-xs text-red-500 hover:underline"
                          >
                            <XCircle className="w-3 h-3" /> Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">No jobs found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </AppLayout>
  );
}
