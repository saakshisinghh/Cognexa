"use client";

/**
 * apps/web/components/agents/WorkflowGraph.tsx
 *
 * Phase 5 — visualizes a multi-agent workflow (sequential / parallel /
 * supervisor) as a React Flow graph: one node per participating agent,
 * color-coded by execution status, laid out left-to-right for
 * sequential/supervisor and stacked in parallel for the parallel mode.
 * Clicking a node surfaces that agent's answer + confidence.
 */
import React, { useMemo, useState } from "react";
import ReactFlow, {
  Background, Controls, Node, Edge, MarkerType, Position,
} from "reactflow";
import "reactflow/dist/style.css";
import { CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import type { WorkflowDetail, WorkflowStep } from "@/types";

const STATUS_COLOR: Record<string, string> = {
  completed: "#22c55e",
  failed: "#ef4444",
  running: "#5b67f1",
  queued: "#94a3b8",
  cancelled: "#f59e0b",
};

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed": return <CheckCircle2 className="w-3.5 h-3.5" style={{ color: STATUS_COLOR.completed }} />;
    case "failed": return <XCircle className="w-3.5 h-3.5" style={{ color: STATUS_COLOR.failed }} />;
    case "running": return <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: STATUS_COLOR.running }} />;
    default: return <Clock className="w-3.5 h-3.5" style={{ color: STATUS_COLOR.queued }} />;
  }
}

export default function WorkflowGraph({ workflow }: { workflow: WorkflowDetail }) {
  const [selected, setSelected] = useState<WorkflowStep | null>(null);

  const { nodes, edges } = useMemo(() => {
    const isParallel = workflow.mode === "parallel";
    const spacingX = 220;
    const spacingY = 120;

    const nodes: Node[] = workflow.steps.map((step, idx) => ({
      id: step.execution_id,
      data: { label: step },
      position: isParallel
        ? { x: idx * spacingX, y: 0 }
        : { x: idx * spacingX, y: (idx % 2) * spacingY * 0.4 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        border: `2px solid ${STATUS_COLOR[step.status] ?? "#94a3b8"}`,
        borderRadius: 12,
        padding: 0,
        background: "hsl(var(--card))",
        width: 190,
      },
    }));

    const edges: Edge[] = isParallel
      ? []
      : workflow.steps.slice(1).map((step, idx) => ({
          id: `e-${idx}`,
          source: workflow.steps[idx].execution_id,
          target: step.execution_id,
          animated: step.status === "running",
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: "hsl(var(--border))" },
        }));

    return { nodes, edges };
  }, [workflow]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 h-96 rounded-xl border border-border overflow-hidden">
        <ReactFlow
          nodes={nodes.map((n) => ({
            ...n,
            data: {
              label: (
                <div
                  className="p-3 cursor-pointer"
                  onClick={() => setSelected((n.data as any).label as WorkflowStep)}
                >
                  <div className="flex items-center gap-1.5">
                    <StatusIcon status={(n.data as any).label.status} />
                    <span className="text-xs font-semibold truncate">{(n.data as any).label.agent_key}</span>
                  </div>
                  {(n.data as any).label.confidence && (
                    <p className="text-[10px] text-muted-foreground mt-1 capitalize">
                      confidence: {(n.data as any).label.confidence.level}
                    </p>
                  )}
                </div>
              ),
            },
          }))}
          edges={edges}
          fitView
          minZoom={0.3}
          maxZoom={1.5}
          nodesDraggable={false}
        >
          <Background gap={16} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <h4 className="text-sm font-semibold mb-2">
          {selected ? `${selected.agent_key} output` : "Select an agent node"}
        </h4>
        {selected ? (
          <div className="space-y-2">
            <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-accent">
              {selected.status}
            </span>
            <p className="text-xs whitespace-pre-wrap leading-relaxed">{selected.answer || "No answer yet."}</p>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Click a node in the workflow graph to inspect its output.</p>
        )}

        {workflow.conflicts.length > 0 && (
          <div className="mt-4 pt-4 border-t border-border">
            <h5 className="text-xs font-semibold text-amber-500 mb-1.5">Conflicts Detected</h5>
            <div className="space-y-1.5">
              {workflow.conflicts.map((c, idx) => (
                <p key={idx} className="text-[11px] text-muted-foreground">
                  <span className="font-medium text-foreground">{c.agents.join(" vs ")}:</span> {c.issue}
                </p>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
