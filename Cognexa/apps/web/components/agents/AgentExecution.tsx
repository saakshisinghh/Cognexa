"use client";

/**
 * apps/web/components/agents/AgentExecution.tsx
 *
 * Phase 5 — full execution detail view: goal, plan, confidence
 * visualization, knowledge sources, final answer, and tabs for the
 * timeline vs raw logs. Used by both the live streaming chat view and
 * the durable execution detail page (app/agents/executions/[id]).
 */
import { useState } from "react";
import { motion } from "framer-motion";
import {
  Gauge, BookOpen, ListChecks, Terminal, Clock, Target, AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import ToolCallTimeline from "./ToolCallTimeline";
import ExecutionLogs from "./ExecutionLogs";
import type { ExecutionDetail, ExecutionStep, AgentConfidence } from "@/types";

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "bg-green-500/10 text-green-500 border-green-500/20",
  medium: "bg-amber-500/10 text-amber-500 border-amber-500/20",
  low: "bg-red-500/10 text-red-500 border-red-500/20",
};

function ConfidenceBar({ confidence }: { confidence: AgentConfidence }) {
  const pct = Math.round((confidence.raw_score ?? 0) * 100);
  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Gauge className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Confidence</span>
        </div>
        <span className={cn("text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border", CONFIDENCE_COLOR[confidence.level] ?? "bg-muted")}>
          {confidence.level}
        </span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          className={cn(
            "h-full rounded-full",
            confidence.level === "high" ? "bg-green-500" : confidence.level === "medium" ? "bg-amber-500" : "bg-red-500"
          )}
        />
      </div>
      <p className="text-[11px] text-muted-foreground">{confidence.explanation}</p>
      {confidence.factors?.has_conflict && (
        <div className="flex items-center gap-1.5 text-[11px] text-amber-500">
          <AlertTriangle className="w-3 h-3" /> Conflicting evidence detected
        </div>
      )}
    </div>
  );
}

export default function AgentExecution({
  execution, liveSteps, liveAnswer,
}: {
  execution: Partial<ExecutionDetail>;
  liveSteps?: ExecutionStep[];
  liveAnswer?: string;
}) {
  const [tab, setTab] = useState<"timeline" | "logs" | "structured">("timeline");
  const steps = liveSteps ?? execution.steps ?? [];
  const answer = liveAnswer ?? execution.answer ?? "";

  return (
    <div className="space-y-4">
      {/* Goal + status */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2">
            <Target className="w-4 h-4 text-primary mt-0.5 shrink-0" />
            <p className="text-sm">{execution.goal}</p>
          </div>
          {execution.status && (
            <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-accent text-muted-foreground shrink-0">
              {execution.status}
            </span>
          )}
        </div>
        {execution.duration_ms != null && (
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground mt-2">
            <Clock className="w-3 h-3" /> {(execution.duration_ms / 1000).toFixed(2)}s
          </div>
        )}
      </div>

      {/* Confidence */}
      {execution.confidence && <ConfidenceBar confidence={execution.confidence as AgentConfidence} />}

      {/* Answer */}
      {answer && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" /> Answer
          </h4>
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{answer}</p>
        </div>
      )}

      {/* Sources */}
      {execution.sources && execution.sources.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h4 className="text-sm font-semibold mb-2">Knowledge Sources ({execution.sources.length})</h4>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {execution.sources.map((s: any, idx: number) => (
              <div key={idx} className="text-[11px] text-muted-foreground border-l-2 border-border pl-2">
                <span className="font-medium text-foreground">{s.document_title || s.incident_id || "Source"}</span>
                {s.excerpt && <p className="mt-0.5 line-clamp-2">{s.excerpt}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs: timeline / logs / structured output */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center gap-1 mb-3 border-b border-border pb-2">
          {[
            { key: "timeline", label: "Timeline", icon: ListChecks },
            { key: "logs", label: "Logs", icon: Terminal },
            { key: "structured", label: "Structured Output", icon: BookOpen },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key as typeof tab)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition",
                tab === t.key ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-accent"
              )}
            >
              <t.icon className="w-3.5 h-3.5" /> {t.label}
            </button>
          ))}
        </div>

        {tab === "timeline" && <ToolCallTimeline steps={steps} live={!!liveSteps} />}
        {tab === "logs" && <ExecutionLogs steps={steps} />}
        {tab === "structured" && (
          <pre className="text-[11px] font-mono bg-background rounded-lg p-3 overflow-x-auto max-h-80 overflow-y-auto">
            {JSON.stringify(execution.structured_output ?? {}, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
