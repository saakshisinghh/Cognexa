

"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import {
  AlertTriangle, TrendingDown, Users, MessageSquareWarning, FileWarning,
  RefreshCw, CheckCircle2, X as XIcon,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";

import AppLayout from "@/components/layout/AppLayout";
import {
  getAssetGaps, getAssetRisks, getDisagreements, getStaleDocuments,
  resolveDisagreement, triggerGapRecompute, triggerLossRecompute,
  triggerDisagreementRecompute, triggerTemporalRecompute,
} from "@/lib/api/knowledge";
import type { RiskLevel, DisagreementSeverity } from "@/lib/types/knowledge";

type Tab = "gaps" | "loss" | "disagreements" | "stale";

const RISK_COLORS: Record<RiskLevel, string> = {
  critical: "#ef4444",
  high: "#f59e0b",
  medium: "#eab308",
  low: "#10b981",
  unknown: "#71717a",
};

const SEVERITY_BADGE: Record<DisagreementSeverity, string> = {
  major: "bg-red-500/10 text-red-400",
  moderate: "bg-amber-500/10 text-amber-400",
  minor: "bg-blue-500/10 text-blue-400",
};

export default function KnowledgeDashboardPage() {
  const [tab, setTab] = useState<Tab>("gaps");
  const queryClient = useQueryClient();

  const gapsQuery = useQuery({ queryKey: ["knowledge", "gaps"], queryFn: () => getAssetGaps(0) });
  const risksQuery = useQuery({ queryKey: ["knowledge", "risks"], queryFn: () => getAssetRisks(0) });
  const disagreementsQuery = useQuery({ queryKey: ["knowledge", "disagreements"], queryFn: () => getDisagreements(false) });
  const staleQuery = useQuery({ queryKey: ["knowledge", "stale"], queryFn: () => getStaleDocuments() });

  const resolveMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes?: string }) => resolveDisagreement(id, notes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge", "disagreements"] }),
  });

  const recomputeAll = async () => {
    await Promise.allSettled([
      triggerTemporalRecompute("trust_scores"),
      triggerGapRecompute(),
      triggerLossRecompute(),
      triggerDisagreementRecompute(),
    ]);
  };

  const highGapCount = (gapsQuery.data ?? []).filter((g) => g.gap_score >= 0.5).length;
  const highRiskCount = (risksQuery.data ?? []).filter((r) => r.risk_level === "high" || r.risk_level === "critical").length;
  const unresolvedCount = (disagreementsQuery.data ?? []).length;
  const staleCount = (staleQuery.data ?? []).length;

  const gapChartData = (gapsQuery.data ?? [])
    .slice()
    .sort((a, b) => b.gap_score - a.gap_score)
    .slice(0, 10)
    .map((g) => ({ name: g.asset_name, score: Math.round(g.gap_score * 100) }));

  const allCategories = Array.from(
    new Set((gapsQuery.data ?? []).flatMap((g) => g.expected_categories))
  ).sort();

  return (
    <AppLayout>
      <div className="p-8 max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Knowledge Dashboard</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Documentation gaps, knowledge-loss risk, and expert disagreements across all assets
            </p>
          </div>
          <button
            onClick={recomputeAll}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground border border-border px-3 py-2 rounded-lg hover:bg-accent transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Recompute all
          </button>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <StatCard icon={TrendingDown} label="Assets with gaps ≥ 50%" value={highGapCount} tone="amber" />
          <StatCard icon={AlertTriangle} label="High/critical loss risk" value={highRiskCount} tone="red" />
          <StatCard icon={MessageSquareWarning} label="Unresolved disagreements" value={unresolvedCount} tone="amber" />
          <StatCard icon={FileWarning} label="Stale documents" value={staleCount} tone="red" />
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-border mb-6">
          {([
            ["gaps", "Documentation Gaps", Users],
            ["loss", "Knowledge Loss Risk", AlertTriangle],
            ["disagreements", "Expert Disagreements", MessageSquareWarning],
            ["stale", "Stale Documents", FileWarning],
          ] as [Tab, string, typeof Users][]).map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {tab === "gaps" && (
          <div className="space-y-6">
            {gapChartData.length > 0 && (
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="text-sm font-semibold text-foreground mb-4">Top 10 assets by GapScore</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={gapChartData} layout="vertical" margin={{ left: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
                    <YAxis type="category" dataKey="name" width={140} tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
                      formatter={(v: number) => [`${v}%`, "GapScore"]}
                    />
                    <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                      {gapChartData.map((d, i) => (
                        <Cell key={i} fill={d.score >= 50 ? "#f59e0b" : "#3b82f6"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {allCategories.length > 0 && (gapsQuery.data?.length ?? 0) > 0 && (
              <div className="bg-card border border-border rounded-xl p-5 overflow-x-auto">
                <h3 className="text-sm font-semibold text-foreground mb-4">Documentation coverage heatmap</h3>
                <table className="text-xs w-full border-collapse">
                  <thead>
                    <tr>
                      <th className="text-left text-muted-foreground font-medium pb-2 pr-4 sticky left-0 bg-card">Asset</th>
                      {allCategories.map((cat) => (
                        <th key={cat} className="text-center text-muted-foreground font-medium pb-2 px-2 whitespace-nowrap capitalize">
                          {cat.replace("_", " ")}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(gapsQuery.data ?? [])
                      .slice()
                      .sort((a, b) => b.gap_score - a.gap_score)
                      .map((g) => (
                        <tr key={g.asset_id} className="border-t border-border">
                          <td className="py-2 pr-4 font-medium text-foreground whitespace-nowrap sticky left-0 bg-card">
                            {g.asset_name}
                          </td>
                          {allCategories.map((cat) => {
                            const present = g.present_categories.includes(cat);
                            return (
                              <td key={cat} className="text-center py-2 px-2">
                                <span
                                  className={`inline-flex w-5 h-5 rounded items-center justify-center ${
                                    present ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"
                                  }`}
                                  title={present ? `${cat}: documented` : `${cat}: missing`}
                                >
                                  {present ? <CheckCircle2 className="w-3 h-3" /> : <XIcon className="w-3 h-3" />}
                                </span>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {(gapsQuery.data ?? []).map((g) => (
                <div key={g.asset_id} className="p-4 border-b border-border last:border-0">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-foreground">{g.asset_name}</span>
                    <span className="text-xs font-semibold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">
                      {Math.round(g.gap_score * 100)}% gap
                    </span>
                  </div>
                  {g.missing_categories.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Missing: {g.missing_categories.join(", ")}
                      {g.incident_penalty_applied && (
                        <span className="text-red-400 ml-2">⚠ has incidents without procedure/manual</span>
                      )}
                    </p>
                  )}
                </div>
              ))}
              {gapsQuery.isSuccess && gapsQuery.data.length === 0 && (
                <EmptyState text="No gap data yet — run the nightly job or trigger a manual recompute." />
              )}
            </div>
          </div>
        )}

        {tab === "loss" && (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {(risksQuery.data ?? []).map((r) => (
              <div key={r.asset_id} className="p-4 border-b border-border last:border-0">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-foreground">{r.asset_name}</span>
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded-full capitalize"
                    style={{ color: RISK_COLORS[r.risk_level], backgroundColor: `${RISK_COLORS[r.risk_level]}1a` }}
                  >
                    {r.risk_level}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mb-1">
                  Primary owner: {r.primary_owner_name ?? "—"} · {r.contributor_count} contributor{r.contributor_count !== 1 ? "s" : ""}
                  {r.retirement_boost_applied && <span className="text-red-400 ml-2">⚠ flagged retirement risk</span>}
                </p>
                {r.mitigation_recommendation && (
                  <p className="text-xs text-foreground/80 mt-2 bg-accent/40 rounded-lg p-2">{r.mitigation_recommendation}</p>
                )}
              </div>
            ))}
            {risksQuery.isSuccess && risksQuery.data.length === 0 && (
              <EmptyState text="No risk data yet — run the nightly job or trigger a manual recompute." />
            )}
          </div>
        )}

        {tab === "disagreements" && (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {(disagreementsQuery.data ?? []).map((d) => (
              <div key={d.id} className="p-4 border-b border-border last:border-0">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-foreground">{d.asset_name ?? d.asset_id} — {d.topic}</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${SEVERITY_BADGE[d.max_severity]}`}>
                    {d.max_severity} · {d.occurrence_count}×
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  "{d.document_a_title}" vs "{d.document_b_title}"
                  {d.last_seen_at && ` · last seen ${formatDistanceToNow(new Date(d.last_seen_at), { addSuffix: true })}`}
                </p>
                <button
                  onClick={() => resolveMutation.mutate({ id: d.id })}
                  disabled={resolveMutation.isPending}
                  className="text-xs text-primary hover:underline flex items-center gap-1"
                >
                  <CheckCircle2 className="w-3 h-3" />
                  Mark resolved
                </button>
              </div>
            ))}
            {disagreementsQuery.isSuccess && disagreementsQuery.data.length === 0 && (
              <EmptyState text="No unresolved disagreements right now." />
            )}
          </div>
        )}

        {tab === "stale" && (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {(staleQuery.data ?? []).map((doc) => (
              <div key={doc.document_id} className="p-4 border-b border-border last:border-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-foreground">{doc.original_filename}</span>
                  <span className="text-xs text-muted-foreground">{doc.category ?? "uncategorized"}</span>
                </div>
                {doc.stale_reason && <p className="text-xs text-muted-foreground">{doc.stale_reason}</p>}
              </div>
            ))}
            {staleQuery.isSuccess && staleQuery.data.length === 0 && (
              <EmptyState text="No stale documents right now." />
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}

function StatCard({ icon: Icon, label, value, tone }: { icon: typeof AlertTriangle; label: string; value: number; tone: "amber" | "red" }) {
  const toneClasses = tone === "amber" ? "bg-amber-500/10 text-amber-400" : "bg-red-500/10 text-red-400";
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-3 ${toneClasses}`}>
        <Icon className="w-4 h-4" />
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="p-8 text-center text-sm text-muted-foreground">{text}</div>;
}
