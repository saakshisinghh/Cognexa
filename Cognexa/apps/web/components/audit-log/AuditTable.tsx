"use client";

import { CheckCircle2, XCircle, ShieldAlert } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import type { AuditLog } from "@/types";

const STATUS_STYLE: Record<string, { icon: typeof CheckCircle2; color: string }> = {
  success: { icon: CheckCircle2, color: "text-green-500" },
  failure: { icon: XCircle, color: "text-red-500" },
  denied: { icon: ShieldAlert, color: "text-amber-500" },
};

interface Props {
  logs: AuditLog[];
  isLoading?: boolean;
  onSelect: (log: AuditLog) => void;
}

export default function AuditTable({ logs, isLoading, onSelect }: Props) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-12 bg-muted/40 rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div className="text-center py-16 text-muted-foreground text-sm">
        No audit events match the current filters.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-3 font-medium">Time</th>
            <th className="px-4 py-3 font-medium">User</th>
            <th className="px-4 py-3 font-medium">Action</th>
            <th className="px-4 py-3 font-medium">Resource</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">IP</th>
            <th className="px-4 py-3 font-medium text-right">Duration</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => {
            const style = STATUS_STYLE[log.status] || STATUS_STYLE.success;
            return (
              <tr
                key={log.id}
                onClick={() => onSelect(log)}
                className="border-t border-border hover:bg-accent/50 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{formatDate(log.timestamp)}</td>
                <td className="px-4 py-3 max-w-[180px] truncate">{log.user_email || "system"}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-medium capitalize">
                    {log.action.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="px-4 py-3 max-w-[220px] truncate text-muted-foreground">{log.resource || "—"}</td>
                <td className="px-4 py-3">
                  <span className={cn("flex items-center gap-1.5 text-xs font-medium", style.color)}>
                    <style.icon className="w-3.5 h-3.5" />
                    {log.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{log.ip_address || "—"}</td>
                <td className="px-4 py-3 text-right text-muted-foreground">
                  {log.duration_ms != null ? `${log.duration_ms.toFixed(0)}ms` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
