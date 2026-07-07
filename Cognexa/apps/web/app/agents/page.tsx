"use client";

/**
 * apps/web/app/agents/page.tsx
 *
 * Phase 5 — Agent Console home: Agent Catalog + inline Run panel.
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import toast from "react-hot-toast";
import { History, Workflow as WorkflowIcon, Bot } from "lucide-react";
import AppLayout from "@/components/layout/AppLayout";
import AgentCard from "@/components/agents/AgentCard";
import AgentChat from "@/components/agents/AgentChat";
import { listAgents, setAgentEnabled } from "@/lib/agents/api";
import { useAuthStore } from "@/store/auth";
import type { AgentDescriptor } from "@/types";

export default function AgentsPage() {
  const { user } = useAuthStore();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<AgentDescriptor | null>(null);

  const { data: agents = [], isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: listAgents,
    refetchInterval: 30000,
  });

  const isAdmin = user?.role === "admin";

  const handleToggle = async (agent: AgentDescriptor) => {
    try {
      await setAgentEnabled(agent.agent_key, !agent.is_enabled);
      toast.success(`${agent.name} ${agent.is_enabled ? "disabled" : "enabled"}`);
      qc.invalidateQueries({ queryKey: ["agents"] });
    } catch {
      toast.error("Failed to update agent");
    }
  };

  return (
    <AppLayout>
      <div className="p-8 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Bot className="w-6 h-6 text-primary" /> Agent Console
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Autonomous specialist agents for root cause analysis, maintenance planning, compliance, and lessons learned.
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              href="/agents/history"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium hover:bg-accent transition"
            >
              <History className="w-3.5 h-3.5" /> History
            </Link>
            <Link
              href="/agents/workflows"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium hover:bg-accent transition"
            >
              <WorkflowIcon className="w-3.5 h-3.5" /> Workflows
            </Link>
          </div>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-40 rounded-xl bg-muted shimmer" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {agents.map((agent) => (
              <AgentCard
                key={agent.agent_key}
                agent={agent}
                onRun={setSelected}
                onToggleEnabled={handleToggle}
                canManage={isAdmin}
              />
            ))}
          </div>
        )}

        {selected && (
          <div className="pt-4 border-t border-border">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold">Running: {selected.name}</h2>
              <button
                onClick={() => setSelected(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Close
              </button>
            </div>
            <AgentChat agent={selected} />
          </div>
        )}
      </div>
    </AppLayout>
  );
}
