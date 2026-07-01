"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import AuditFilters from "@/components/audit-log/AuditFilters";
import AuditTable from "@/components/audit-log/AuditTable";
import AuditTimeline from "@/components/audit-log/AuditTimeline";
import AuditDrawer from "@/components/audit-log/AuditDrawer";
import type { AuditLog, AuditFilters as Filters } from "@/types";
import { ChevronLeft, ChevronRight, List, GanttChartSquare, Download, ShieldCheck } from "lucide-react";

interface AuditListResponse {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export default function AuditLogsPage() {
  const [filters, setFilters] = useState<Filters>({});
  const [page, setPage] = useState(1);
  const [view, setView] = useState<"table" | "timeline">("table");
  const [selected, setSelected] = useState<AuditLog | null>(null);

  const { data, isLoading } = useQuery<AuditListResponse>({
    queryKey: ["audit-logs", filters, page],
    queryFn: () =>
      api.get("/audit", { params: { ...filters, page, page_size: 50 } }).then((r) => r.data),
    refetchInterval: 15_000,
  });

  const exportLogs = (format: "csv" | "json") => {
    const params = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v) as [string, string][]
    ).toString();
    const url = `${api.defaults.baseURL}/audit/export.${format}${params ? `?${params}` : ""}`;
    window.open(url, "_blank");
  };

  return (
    <AppLayout>
      <div className="p-8 max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold">Audit Logs</h1>
              <p className="text-sm text-muted-foreground">{data?.total ?? 0} events recorded</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center rounded-lg border border-border overflow-hidden">
              <button
                onClick={() => setView("table")}
                className={`p-2 ${view === "table" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-accent"}`}
              >
                <List className="w-4 h-4" />
              </button>
              <button
                onClick={() => setView("timeline")}
                className={`p-2 ${view === "timeline" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-accent"}`}
              >
                <GanttChartSquare className="w-4 h-4" />
              </button>
            </div>
            <button
              onClick={() => exportLogs("csv")}
              className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-border hover:bg-accent"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
            <button
              onClick={() => exportLogs("json")}
              className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-border hover:bg-accent"
            >
              <Download className="w-3.5 h-3.5" /> JSON
            </button>
          </div>
        </div>

        <AuditFilters filters={filters} onChange={(f) => { setFilters(f); setPage(1); }} />

        {view === "table" ? (
          <AuditTable logs={data?.items || []} isLoading={isLoading} onSelect={setSelected} />
        ) : (
          <AuditTimeline logs={data?.items || []} isLoading={isLoading} onSelect={setSelected} />
        )}

        {data && data.pages > 1 && (
          <div className="flex items-center justify-between text-sm">
            <p className="text-muted-foreground">
              Page {data.page} of {data.pages}
            </p>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="p-2 rounded-lg border border-border disabled:opacity-40 hover:bg-accent"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                disabled={page >= data.pages}
                onClick={() => setPage((p) => p + 1)}
                className="p-2 rounded-lg border border-border disabled:opacity-40 hover:bg-accent"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      <AuditDrawer log={selected} onClose={() => setSelected(null)} />
    </AppLayout>
  );
}
