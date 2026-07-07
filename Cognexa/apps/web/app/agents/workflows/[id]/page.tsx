"use client";

/**
 * apps/web/app/agents/workflows/[id]/page.tsx
 *
 * Phase 5 — workflow detail: React Flow visualization of participating
 * agents, their statuses, the synthesized final answer, and any
 * detected conflicts between agent outputs.
 */
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, BookOpen } from "lucide-react";
import AppLayout from "@/components/layout/AppLayout";
import WorkflowGraph from "@/components/agents/WorkflowGraph";
import { getWorkflow } from "@/lib/agents/api";

export default function WorkflowDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: workflow, isLoading, error } = useQuery({
    queryKey: ["agent-workflow", params.id],
    queryFn: () => getWorkflow(params.id),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  });

  return (
    <AppLayout>
      <div className="p-8 max-w-5xl mx-auto space-y-4">
        <Link href="/agents/workflows" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to workflows
        </Link>

        {isLoading && <div className="h-96 rounded-xl bg-muted shimmer" />}
        {error && <p className="text-sm text-red-500">Failed to load workflow.</p>}

        {workflow && (
          <>
            <div>
              <h1 className="text-xl font-bold">{workflow.goal}</h1>
              <p className="text-xs text-muted-foreground mt-1 capitalize">
                {workflow.mode} · {workflow.status} · {workflow.agent_keys.length} agents
              </p>
            </div>

            <WorkflowGraph workflow={workflow} />

            {workflow.final_answer && (
              <div className="rounded-xl border border-border bg-card p-4">
                <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <BookOpen className="w-4 h-4 text-primary" /> Synthesized Answer
                </h4>
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{workflow.final_answer}</p>
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
