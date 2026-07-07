"use client";

/**
 * apps/web/components/agents/AgentChat.tsx
 *
 * Phase 5 — the primary "Run Agent" interface: a goal input plus a live
 * streaming view of the agent's execution (reasoning, tool calls,
 * confidence, final answer) as it happens, powered by
 * lib/agents/api.ts::runAgentStream (SSE).
 */
import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { Send, Loader2, StopCircle, Sparkles } from "lucide-react";
import { runAgentStream } from "@/lib/agents/api";
import AgentExecution from "./AgentExecution";
import type { AgentDescriptor, ExecutionStep, AgentConfidence, ExecutionDetail } from "@/types";

export default function AgentChat({ agent }: { agent: AgentDescriptor }) {
  const [goal, setGoal] = useState("");
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  const [answer, setAnswer] = useState("");
  const [confidence, setConfidence] = useState<AgentConfidence | undefined>();
  const [structuredOutput, setStructuredOutput] = useState<Record<string, unknown> | undefined>();
  const [executionId, setExecutionId] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();
  const cancelRef = useRef<() => void>();

  const startRun = () => {
    if (!goal.trim() || running) return;
    setRunning(true);
    setSteps([]);
    setAnswer("");
    setConfidence(undefined);
    setStructuredOutput(undefined);
    setError(undefined);

    const { cancel } = runAgentStream(
      agent.agent_key, goal, {},
      (event) => {
        if (event.type === "node") {
          const newSteps = event.output.execution_history ?? [];
          if (newSteps.length) setSteps((prev) => [...prev, ...newSteps]);
          if (event.output.answer) setAnswer(event.output.answer);
          if (event.output.confidence) setConfidence(event.output.confidence as AgentConfidence);
          if (event.output.structured_output) setStructuredOutput(event.output.structured_output);
        } else if (event.type === "done") {
          setExecutionId(event.execution_id);
          setRunning(false);
        } else if (event.type === "error") {
          setError(event.message);
          setRunning(false);
        }
      },
      (message) => {
        setError(message);
        setRunning(false);
      },
    );
    cancelRef.current = cancel;
  };

  const stopRun = () => {
    cancelRef.current?.();
    setRunning(false);
  };

  const partialExecution: Partial<ExecutionDetail> = {
    goal, status: running ? "running" : executionId ? "completed" : undefined,
    confidence: confidence ?? null, structured_output: structuredOutput ?? null,
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold">Run {agent.name}</h3>
        </div>
        <div className="flex gap-2">
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder={`e.g. "Why did pump P-1045 fail last week?"`}
            rows={2}
            disabled={running}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                startRun();
              }
            }}
            className="flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
          />
          {running ? (
            <button
              onClick={stopRun}
              className="inline-flex items-center gap-1.5 rounded-lg bg-destructive text-destructive-foreground px-4 py-2 text-sm font-medium hover:opacity-90 transition h-fit"
            >
              <StopCircle className="w-4 h-4" /> Stop
            </button>
          ) : (
            <button
              onClick={startRun}
              disabled={!goal.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:opacity-90 transition disabled:opacity-40 h-fit"
            >
              <Send className="w-4 h-4" /> Run
            </button>
          )}
        </div>
        {running && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-2">
            <Loader2 className="w-3 h-3 animate-spin" /> Agent is working…
          </div>
        )}
        {error && <p className="text-xs text-red-500 mt-2">{error}</p>}
      </div>

      {(steps.length > 0 || answer) && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <AgentExecution execution={partialExecution} liveSteps={steps} liveAnswer={answer} />
        </motion.div>
      )}
    </div>
  );
}
