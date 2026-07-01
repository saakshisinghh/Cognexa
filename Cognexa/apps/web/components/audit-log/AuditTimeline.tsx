"use client";

import { motion } from "framer-motion";
import { CheckCircle2, XCircle, ShieldAlert, Circle } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import type { AuditLog } from "@/types";

const STATUS_DOT: Record<string, string> = {
  success: "bg-green-500",
  failure: "bg-red-500",
  denied: "bg-amber-500",
};

const STATUS_ICON: Record<string, typeof CheckCircle2> = {
  success: CheckCircle2,
  failure: XCircle,
  denied: ShieldAlert,
};

interface Props {
  logs: AuditLog[];
  isLoading?: boolean;
  onSelect: (log: AuditLog) => void;
}

export default function AuditTimeline({ logs, isLoading, onSelect }: Props) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-16 bg-muted/40 rounded-lg animate-pulse" />
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
    <div className="relative pl-6">
      <div className="absolute left-2 top-2 bottom-2 w-px bg-border" />
      <div className="space-y-3">
        {logs.map((log, i) => {
          const Icon = STATUS_ICON[log.status] || Circle;
          return (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(i * 0.02, 0.3) }}
              onClick={() => onSelect(log)}
              className="relative cursor-pointer group"
            >
              <div className={cn("absolute -left-[26px] top-3 w-3 h-3 rounded-full ring-4 ring-background", STATUS_DOT[log.status] || "bg-muted-foreground")} />
              <div className="p-3 rounded-xl border border-border bg-card group-hover:border-primary/40 transition-colors">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <Icon className="w-4 h-4 shrink-0 text-muted-foreground" />
                    <span className="font-medium text-sm capitalize truncate">
                      {log.action.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs text-muted-foreground truncate">
                      {log.user_email || "system"}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground shrink-0">{formatDate(log.timestamp)}</span>
                </div>
                {log.resource && (
                  <p className="mt-1 text-xs text-muted-foreground truncate">{log.resource}</p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
