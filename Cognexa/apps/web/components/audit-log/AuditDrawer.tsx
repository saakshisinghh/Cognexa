"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { formatDate } from "@/lib/utils";
import type { AuditLog } from "@/types";

interface Props {
  log: AuditLog | null;
  onClose: () => void;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-border last:border-0">
      <span className="text-xs text-muted-foreground shrink-0 w-32">{label}</span>
      <span className="text-sm text-right break-all">{value ?? "—"}</span>
    </div>
  );
}

export default function AuditDrawer({ log, onClose }: Props) {
  return (
    <AnimatePresence>
      {log && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/40 z-40"
          />
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-card border-l border-border z-50 overflow-y-auto"
          >
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="font-semibold capitalize">{log.action.replace(/_/g, " ")}</h3>
              <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-accent">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-1">
              <Row label="Timestamp" value={formatDate(log.timestamp)} />
              <Row label="User" value={log.user_email} />
              <Row label="Role" value={log.role} />
              <Row label="Status" value={<span className="capitalize">{log.status}</span>} />
              <Row label="Resource" value={log.resource} />
              <Row label="IP Address" value={log.ip_address} />
              <Row label="User Agent" value={<span className="text-xs">{log.user_agent}</span>} />
              <Row label="Duration" value={log.duration_ms != null ? `${log.duration_ms.toFixed(1)} ms` : null} />
              <Row label="Correlation ID" value={<span className="text-xs font-mono">{log.correlation_id}</span>} />
              {log.detail && <Row label="Detail" value={log.detail} />}
            </div>
            {(log.old_value != null || log.new_value != null) && (
              <div className="p-5 border-t border-border space-y-3">
                {log.old_value != null && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Old value</p>
                    <pre className="text-xs bg-muted/50 rounded-lg p-3 overflow-x-auto">
                      {JSON.stringify(log.old_value, null, 2)}
                    </pre>
                  </div>
                )}
                {log.new_value != null && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">New value</p>
                    <pre className="text-xs bg-muted/50 rounded-lg p-3 overflow-x-auto">
                      {JSON.stringify(log.new_value, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
