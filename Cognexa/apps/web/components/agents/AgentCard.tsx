"use client";

/**
 * apps/web/components/agents/AgentCard.tsx
 *
 * Phase 5 — Agent Catalog card. Shows one registered agent with its
 * health/enabled status, capabilities, and a "Run" call to action.
 */
import { motion } from "framer-motion";
import { Activity, CheckCircle2, AlertTriangle, XCircle, HelpCircle, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentDescriptor } from "@/types";

const HEALTH_ICON: Record<string, React.ElementType> = {
  ok: CheckCircle2,
  degraded: AlertTriangle,
  error: XCircle,
  unknown: HelpCircle,
};

const HEALTH_COLOR: Record<string, string> = {
  ok: "text-green-500",
  degraded: "text-amber-500",
  error: "text-red-500",
  unknown: "text-muted-foreground",
};

export default function AgentCard({
  agent, onRun, onToggleEnabled, canManage,
}: {
  agent: AgentDescriptor;
  onRun: (agent: AgentDescriptor) => void;
  onToggleEnabled?: (agent: AgentDescriptor) => void;
  canManage?: boolean;
}) {
  const HealthIcon = HEALTH_ICON[agent.health_status] ?? HelpCircle;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-xl border border-border bg-card p-5 flex flex-col gap-3 transition-all",
        !agent.is_enabled && "opacity-60"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-sm">{agent.name}</h3>
          <p className="text-[11px] text-muted-foreground mt-0.5">v{agent.version} · {agent.agent_key}</p>
        </div>
        <div className={cn("flex items-center gap-1 text-xs", HEALTH_COLOR[agent.health_status])}>
          <HealthIcon className="w-3.5 h-3.5" />
          <span className="capitalize">{agent.health_status}</span>
        </div>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">{agent.description}</p>

      <div className="flex flex-wrap gap-1.5">
        {agent.capabilities.slice(0, 5).map((cap) => (
          <span
            key={cap}
            className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[10px] text-muted-foreground"
          >
            <Wrench className="w-2.5 h-2.5" /> {cap}
          </span>
        ))}
        {agent.capabilities.length > 5 && (
          <span className="text-[10px] text-muted-foreground px-1">+{agent.capabilities.length - 5} more</span>
        )}
      </div>

      <div className="flex items-center gap-2 mt-2">
        <button
          onClick={() => onRun(agent)}
          disabled={!agent.is_enabled}
          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium py-2 hover:opacity-90 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Activity className="w-3.5 h-3.5" /> Run Agent
        </button>
        {canManage && onToggleEnabled && (
          <button
            onClick={() => onToggleEnabled(agent)}
            className="rounded-lg border border-border px-3 py-2 text-xs font-medium hover:bg-accent transition"
          >
            {agent.is_enabled ? "Disable" : "Enable"}
          </button>
        )}
      </div>
    </motion.div>
  );
}
