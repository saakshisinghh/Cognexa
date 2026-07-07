"use client";

/**
 * apps/web/app/agents/workflows/page.tsx
 *
 * Phase 5 — multi-agent workflow runner: pick 2+ agents, a mode
 * (sequential / parallel / supervisor), and a goal, then run and jump
 * to the resulting workflow's detail view.
 */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { ArrowLeft, Workflow as WorkflowIcon, Loader2 } from "lucide-react";
import Link from "next/link";
import AppLayout from "@/components/layout/AppLayout";
import { listAgents, runWorkflow } from "@/lib/agents/api";
import { cn } from "@/lib/utils";
import type { AgentExecutionMode } from "@/types";

const MODES: { key: AgentExecutionMode; label: string; description: string }[] = [
  { key: "sequential", label: "Sequential", description: "Agents run one after another, each sees prior findings." },
  { key: "parallel", label: "Parallel", description: "All agents run independently at the same time." },
  { key: "supervisor", label: "Supervisor", description: "An LLM supervisor decides which agents to invoke and in what order." },
];

export default function WorkflowsPage() {
  const router = useRouter();
  const { data: agents = [] } = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const [goal, setGoal] = useState("");
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [mode, setMode] = useState<AgentExecutionMode>("sequential");
  const [running, setRunning] = useState(false);

  const toggleAgent = (key: string) => {
    setSelectedAgents((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  };

  const handleRun = async () => {
    if (!goal.trim() || selectedAgents.length === 0) return;
    setRunning(true);
    try {
      const workflow = await runWorkflow(goal, selectedAgents, mode);
      router.push(`/agents/workflows/${workflow.workflow_id}`);
    } catch {
      toast.error("Failed to run workflow");
      setRunning(false);
    }
  };

  return (
    <AppLayout>
      <div className="p-8 max-w-3xl mx-auto space-y-6">
        <Link href="/agents" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Agent Console
        </Link>

        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <WorkflowIcon className="w-6 h-6 text-primary" /> Multi-Agent Workflow
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Coordinate multiple specialist agents on a single goal.
          </p>
        </div>

        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Goal</label>
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={2}
              placeholder="e.g. Investigate the P-1045 pump failure and update the maintenance plan"
              className="w-full mt-1 resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground">Agents</label>
            <div className="flex flex-wrap gap-2 mt-1.5">
              {agents.map((a) => (
                <button
                  key={a.agent_key}
                  onClick={() => toggleAgent(a.agent_key)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                    selectedAgents.includes(a.agent_key)
                      ? "bg-primary/10 border-primary text-primary"
                      : "border-border text-muted-foreground hover:bg-accent"
                  )}
                >
                  {a.name}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground">Collaboration mode</label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-1.5">
              {MODES.map((m) => (
                <button
                  key={m.key}
                  onClick={() => setMode(m.key)}
                  className={cn(
                    "text-left rounded-lg border px-3 py-2 transition",
                    mode === m.key ? "border-primary bg-primary/5" : "border-border hover:bg-accent"
                  )}
                >
                  <p className="text-xs font-semibold">{m.label}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">{m.description}</p>
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleRun}
            disabled={!goal.trim() || selectedAgents.length === 0 || running}
            className="w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary text-primary-foreground py-2.5 text-sm font-medium hover:opacity-90 transition disabled:opacity-40"
          >
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <WorkflowIcon className="w-4 h-4" />}
            Run Workflow
          </button>
        </div>
      </div>
    </AppLayout>
  );
}