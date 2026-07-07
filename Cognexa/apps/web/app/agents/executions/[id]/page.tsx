"use client";

/**
 * apps/web/app/agents/executions/[id]/page.tsx
 *
 * Phase 5 — durable execution detail view (post-hoc inspection of a
 * completed/failed/cancelled run), reusing the same AgentExecution
 * component the live streaming chat uses.
 */
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import AppLayout from "@/components/layout/AppLayout";
import AgentExecution from "@/components/agents/AgentExecution";
import { getExecution } from "@/lib/agents/api";

export default function ExecutionDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: execution, isLoading, error } = useQuery({
    queryKey: ["agent-execution", params.id],
    queryFn: () => getExecution(params.id),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  });

  return (
    <AppLayout>
      <div className="p-8 max-w-3xl mx-auto space-y-4">
        <Link href="/agents/history" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to history
        </Link>

        {isLoading && <div className="h-40 rounded-xl bg-muted shimmer" />}
        {error && <p className="text-sm text-red-500">Failed to load execution.</p>}
        {execution && (
          <>
            <h1 className="text-xl font-bold">{execution.agent_key}</h1>
            <AgentExecution execution={execution} />
          </>
        )}
      </div>
    </AppLayout>
  );
}
