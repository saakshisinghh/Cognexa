"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Link from "next/link";
import toast from "react-hot-toast";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import { formatBytes, formatDate, formatRelativeTime, cn } from "@/lib/utils";
import type { Asset, AssetStats, PaginatedResponse, Document } from "@/types";
import { getAssetTimeline } from "@/lib/api/timeline";
import type { TimelineEventType } from "@/lib/types/knowledge";
import {
  ArrowLeft, Factory, ChevronRight, MapPin, Tag, FileText,
  Activity, BarChart3, Layers, MessageSquare, CheckCircle2,
  AlertCircle, Loader2, Clock, Edit2, Trash2, X,
  AlertOctagon, Wrench, ClipboardCheck, History,
} from "lucide-react";

const HEALTH_COLORS: Record<string, string> = {
  healthy: "text-green-500 bg-green-500/10 border-green-500/20",
  warning: "text-yellow-500 bg-yellow-500/10 border-yellow-500/20",
  critical: "text-red-500 bg-red-500/10 border-red-500/20",
  unknown: "text-muted-foreground bg-muted border-border",
};

const STATUS_ICONS: Record<string, JSX.Element> = {
  completed: <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />,
  processing: <Loader2 className="w-3.5 h-3.5 text-yellow-500 animate-spin" />,
  failed: <AlertCircle className="w-3.5 h-3.5 text-red-500" />,
  pending: <Clock className="w-3.5 h-3.5 text-muted-foreground" />,
};

const TABS = ["Overview", "Documents", "Statistics", "Time-Machine"] as const;
type Tab = (typeof TABS)[number];

const EVENT_ICON: Record<TimelineEventType, typeof FileText> = {
  incident: AlertOctagon,
  document: FileText,
  work_order: Wrench,
  inspection: ClipboardCheck,
  knowledge_superseded: History,
};

const EVENT_COLOR: Record<TimelineEventType, string> = {
  incident: "text-red-400 bg-red-500/10",
  document: "text-blue-400 bg-blue-500/10",
  work_order: "text-violet-400 bg-violet-500/10",
  inspection: "text-teal-400 bg-teal-500/10",
  knowledge_superseded: "text-amber-400 bg-amber-500/10",
};

export default function AssetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("Overview");

  const { data: asset, isLoading } = useQuery<Asset>({
    queryKey: ["asset", id],
    queryFn: () => api.get(`/assets/${id}`).then((r) => r.data),
  });

  const { data: stats } = useQuery<AssetStats>({
    queryKey: ["asset-stats", id],
    queryFn: () => api.get(`/assets/${id}/stats`).then((r) => r.data),
    enabled: activeTab === "Statistics",
  });

  const { data: docsData } = useQuery<PaginatedResponse<Document>>({
    queryKey: ["asset-docs", id],
    queryFn: () => api.get(`/assets/${id}/documents`).then((r) => r.data),
    enabled: activeTab === "Documents",
  });

  const { data: timeline, isLoading: timelineLoading } = useQuery({
    queryKey: ["asset-timeline", id],
    queryFn: () => getAssetTimeline(id),
    enabled: activeTab === "Time-Machine",
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/assets/${id}`),
    onSuccess: () => {
      toast.success("Asset deleted");
      router.push("/assets");
    },
  });

  if (isLoading) {
    return (
      <AppLayout>
        <div className="p-8 animate-pulse">
          <div className="h-8 bg-muted rounded w-48 mb-6" />
          <div className="h-32 bg-muted rounded-xl" />
        </div>
      </AppLayout>
    );
  }

  if (!asset) {
    return (
      <AppLayout>
        <div className="p-8 text-center text-muted-foreground">Asset not found</div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="p-8">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
          <Link href="/assets" className="hover:text-foreground transition flex items-center gap-1">
            <ArrowLeft className="w-3.5 h-3.5" />
            Assets
          </Link>
          <ChevronRight className="w-3.5 h-3.5" />
          <span className="text-foreground">{asset.name}</span>
        </div>

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 bg-purple-500/10 rounded-2xl flex items-center justify-center shrink-0">
              <Factory className="w-7 h-7 text-purple-500" />
            </div>
            <div>
              <div className="flex items-center gap-3 mb-1">
                <h1 className="text-2xl font-bold">{asset.name}</h1>
                <span className={cn(
                  "px-2.5 py-1 rounded-full text-xs font-medium border capitalize",
                  HEALTH_COLORS[asset.health_status] ?? HEALTH_COLORS.unknown
                )}>
                  {asset.health_status}
                </span>
              </div>
              <div className="flex items-center gap-4 text-sm text-muted-foreground">
                {asset.asset_type && <span className="capitalize">{asset.asset_type}</span>}
                {asset.location && (
                  <span className="flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5" />{asset.location}
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <FileText className="w-3.5 h-3.5" />{asset.document_count} docs
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href={`/copilot?asset=${id}`}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition"
            >
              <MessageSquare className="w-4 h-4" />
              Ask Copilot
            </Link>
            <button
              onClick={() => { if (confirm("Delete this asset? Documents will be unlinked.")) deleteMutation.mutate(); }}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:bg-destructive/10 hover:text-destructive text-sm transition"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Quick stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          {[
            { label: "Documents", value: asset.document_count, icon: FileText },
            { label: "Tags", value: asset.tags?.length ?? 0, icon: Tag },
            { label: "Created", value: formatRelativeTime(asset.created_at), icon: Clock },
            { label: "Updated", value: formatRelativeTime(asset.updated_at), icon: Activity },
          ].map((s) => (
            <div key={s.label} className="bg-card border border-border rounded-lg p-3 flex items-center gap-3">
              <div className="w-8 h-8 bg-purple-500/10 rounded-lg flex items-center justify-center">
                <s.icon className="w-4 h-4 text-purple-500" />
              </div>
              <div>
                <p className="text-base font-bold leading-none">{s.value}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{s.label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-border mb-6">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition",
                activeTab === tab
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {activeTab === "Overview" && (
            <div className="grid lg:grid-cols-2 gap-6">
              <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                <h3 className="font-semibold">Asset Details</h3>
                {[
                  ["Name", asset.name],
                  ["Type", asset.asset_type ?? "—"],
                  ["Location", asset.location ?? "—"],
                  ["Health", asset.health_status],
                  ["Status", asset.is_active ? "Active" : "Inactive"],
                  ["Created", formatDate(asset.created_at)],
                  ["Updated", formatDate(asset.updated_at)],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between py-2 border-b border-border last:border-0">
                    <span className="text-sm text-muted-foreground">{label}</span>
                    <span className="text-sm font-medium capitalize">{value}</span>
                  </div>
                ))}
              </div>

              <div className="space-y-5">
                {asset.description && (
                  <div className="bg-card border border-border rounded-xl p-5">
                    <h3 className="font-semibold mb-3">Description</h3>
                    <p className="text-sm text-muted-foreground leading-relaxed">{asset.description}</p>
                  </div>
                )}

                {asset.tags?.length > 0 && (
                  <div className="bg-card border border-border rounded-xl p-5">
                    <h3 className="font-semibold mb-3">Tags</h3>
                    <div className="flex flex-wrap gap-2">
                      {asset.tags.map((tag) => (
                        <span key={tag} className="px-2.5 py-1 bg-primary/10 text-primary rounded-full text-xs flex items-center gap-1">
                          <Tag className="w-3 h-3" />{tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "Documents" && (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {!docsData || docsData.items.length === 0 ? (
                <div className="p-12 text-center text-muted-foreground">
                  <FileText className="w-10 h-10 mx-auto mb-3" />
                  <p>No documents linked to this asset</p>
                  <Link href="/documents" className="text-primary text-sm hover:underline mt-2 inline-block">
                    Upload documents
                  </Link>
                </div>
              ) : (
                docsData.items.map((doc) => (
                  <Link
                    key={doc.id}
                    href={`/documents/${doc.id}`}
                    className="flex items-center gap-4 px-5 py-4 border-b border-border hover:bg-accent/30 transition group"
                  >
                    <div className="w-8 h-8 bg-primary/10 rounded flex items-center justify-center">
                      <FileText className="w-4 h-4 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover:text-primary transition">
                        {doc.original_filename}
                      </p>
                      <p className="text-xs text-muted-foreground">{formatRelativeTime(doc.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {STATUS_ICONS[doc.status] ?? STATUS_ICONS.pending}
                      <span className="text-xs text-muted-foreground capitalize">{doc.status}</span>
                    </div>
                  </Link>
                ))
              )}
            </div>
          )}

          {activeTab === "Statistics" && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {stats ? (
                [
                  { label: "Total Documents", value: stats.total_documents, color: "bg-blue-500/10 text-blue-500" },
                  { label: "Completed", value: stats.completed_documents, color: "bg-green-500/10 text-green-500" },
                  { label: "Processing", value: stats.processing_documents, color: "bg-yellow-500/10 text-yellow-500" },
                  { label: "Failed", value: stats.failed_documents, color: "bg-red-500/10 text-red-500" },
                  { label: "Total Chunks", value: stats.total_chunks, color: "bg-purple-500/10 text-purple-500" },
                  { label: "Storage Used", value: formatBytes(stats.total_storage_bytes), color: "bg-slate-500/10 text-slate-400" },
                ].map((s) => (
                  <div key={s.label} className="bg-card border border-border rounded-xl p-5">
                    <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center mb-3", s.color.split(" ")[0])}>
                      <BarChart3 className={cn("w-5 h-5", s.color.split(" ")[1])} />
                    </div>
                    <p className="text-2xl font-bold">{s.value}</p>
                    <p className="text-sm text-muted-foreground mt-1">{s.label}</p>
                  </div>
                ))
              ) : (
                <div className="col-span-3 flex items-center justify-center py-12">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              )}
            </div>
          )}
          {activeTab === "Time-Machine" && (
            <div className="bg-card border border-border rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold">Incident, document & knowledge timeline</h3>
                <Link href={`/time-machine`} className="text-xs text-primary hover:underline">
                  Open full Time Machine (with replay) →
                </Link>
              </div>

              {timelineLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : !timeline || timeline.events.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground">
                  <History className="w-10 h-10 mx-auto mb-3" />
                  <p>No timeline events for this asset yet</p>
                </div>
              ) : (
                <div className="space-y-0">
                  {timeline.events.map((event, i) => {
                    const Icon = EVENT_ICON[event.event_type];
                    return (
                      <div key={i} className="flex gap-3 pb-6 relative">
                        {i < timeline.events.length - 1 && (
                          <div className="absolute left-4 top-8 bottom-0 w-px bg-border" />
                        )}
                        <div className={cn("w-8 h-8 rounded-full flex items-center justify-center shrink-0", EVENT_COLOR[event.event_type])}>
                          <Icon className="w-4 h-4" />
                        </div>
                        <div className="flex-1 min-w-0 pt-1">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium">{event.title}</span>
                            <span className="text-[10px] text-muted-foreground shrink-0 ml-2">
                              {formatDate(event.occurred_at)}
                            </span>
                          </div>
                          {event.description && (
                            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{event.description}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </motion.div>
      </div>
    </AppLayout>
  );
}
