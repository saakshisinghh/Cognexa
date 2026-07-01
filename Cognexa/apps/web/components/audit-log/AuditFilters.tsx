"use client";

import { Search, X } from "lucide-react";
import type { AuditFilters as Filters } from "@/types";

const ACTIONS = [
  "login", "logout", "login_failed", "upload", "delete", "rename",
  "search", "chat_query", "download", "role_change", "asset_update",
  "settings_change", "api_error", "reprocess", "retry_task", "cancel_task",
];

const STATUSES = ["success", "failure", "denied"];

interface Props {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

export default function AuditFilters({ filters, onChange }: Props) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const hasActive = Object.values(filters).some(Boolean);

  return (
    <div className="flex flex-wrap items-center gap-2 p-4 bg-card border border-border rounded-xl">
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={filters.search || ""}
          onChange={(e) => set({ search: e.target.value || undefined })}
          placeholder="Search user, resource, detail…"
          className="w-full pl-9 pr-3 py-2 text-sm rounded-lg bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
      </div>

      <select
        value={filters.action || ""}
        onChange={(e) => set({ action: e.target.value || undefined })}
        className="px-3 py-2 text-sm rounded-lg bg-background border border-border focus:outline-none"
      >
        <option value="">All actions</option>
        {ACTIONS.map((a) => (
          <option key={a} value={a}>{a.replace(/_/g, " ")}</option>
        ))}
      </select>

      <select
        value={filters.status || ""}
        onChange={(e) => set({ status: e.target.value || undefined })}
        className="px-3 py-2 text-sm rounded-lg bg-background border border-border focus:outline-none"
      >
        <option value="">All statuses</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>

      <input
        type="date"
        value={filters.date_from ? filters.date_from.slice(0, 10) : ""}
        onChange={(e) => set({ date_from: e.target.value ? `${e.target.value}T00:00:00Z` : undefined })}
        className="px-3 py-2 text-sm rounded-lg bg-background border border-border focus:outline-none"
      />
      <span className="text-muted-foreground text-xs">to</span>
      <input
        type="date"
        value={filters.date_to ? filters.date_to.slice(0, 10) : ""}
        onChange={(e) => set({ date_to: e.target.value ? `${e.target.value}T23:59:59Z` : undefined })}
        className="px-3 py-2 text-sm rounded-lg bg-background border border-border focus:outline-none"
      />

      {hasActive && (
        <button
          onClick={() => onChange({})}
          className="flex items-center gap-1 px-3 py-2 text-xs text-muted-foreground hover:text-foreground rounded-lg hover:bg-accent"
        >
          <X className="w-3.5 h-3.5" /> Clear
        </button>
      )}
    </div>
  );
}
