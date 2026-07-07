"use client";

/**
 * apps/web/components/agents/ToolCallTimeline.tsx
 *
 * Phase 5 — renders an agent execution's step-by-step timeline
 * (Planner -> Retriever -> Graph Query -> Tool Executor -> Reasoner ->
 * Validator -> Response Generator), including retries, as a vertical
 * timeline. Used by both the live streaming view (AgentChat) and the
 * durable execution detail view (AgentExecution / ExecutionLogs).
 */
import { motion } from "framer-motion";
import {
  Brain, Search, Network, Wrench, Lightbulb, ShieldCheck, FileOutput,
  CheckCircle2, XCircle, RotateCcw, Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ExecutionStep } from "@/types";

function iconFor(step: string) {
  if (step.startsWith("planner")) return Brain;
  if (step.startsWith("retriever")) return Search;
  if (step.startsWith("graph_query")) return Network;
  if (step.startsWith("tool:")) return Wrench;
  if (step.startsWith("reasoner")) return Lightbulb;
  if (step.startsWith("validator")) return ShieldCheck;
  if (step.startsWith("response_generator")) return FileOutput;
  return Loader2;
}

function statusIcon(status: string) {
  switch (status) {
    case "completed": return <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />;
    case "failed": return <XCircle className="w-3.5 h-3.5 text-red-500" />;
    case "retried": return <RotateCcw className="w-3.5 h-3.5 text-amber-500" />;
    default: return <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />;
  }
}

export default function ToolCallTimeline({ steps, live }: { steps: ExecutionStep[]; live?: boolean }) {
  if (steps.length === 0) {
    return <p className="text-xs text-muted-foreground italic">No steps recorded yet.</p>;
  }

  return (
    <div className="relative pl-6">
      <div className="absolute left-[9px] top-1 bottom-1 w-px bg-border" />
      <div className="space-y-4">
        {steps.map((step, idx) => {
          const Icon = iconFor(step.step);
          return (
            <motion.div
              key={`${step.step}-${idx}`}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: live ? 0 : idx * 0.02 }}
              className="relative flex gap-3"
            >
              <div className="absolute -left-6 top-0.5 w-4.5 h-4.5 rounded-full bg-card border border-border flex items-center justify-center">
                <Icon className="w-2.5 h-2.5 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium font-mono truncate">{step.step}</span>
                  {statusIcon(step.status)}
                  {typeof step.duration_ms === "number" && (
                    <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
                      {step.duration_ms.toFixed(0)}ms
                    </span>
                  )}
                </div>
                {step.detail && (
                  <p className="text-[11px] text-muted-foreground mt-0.5 break-words">{step.detail}</p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
