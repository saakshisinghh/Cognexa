"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Link from "next/link";
import toast from "react-hot-toast";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import { formatBytes, formatDate, cn } from "@/lib/utils";
import type { DocumentDetail } from "@/types";
import {
  ArrowLeft, FileText, CheckCircle2, AlertCircle, Loader2,
  Clock, Hash, Globe, Tag, Download, RefreshCw, Trash2,
  ChevronRight, Eye, MessageSquare, Layers, BookOpen
} from "lucide-react";

const STATUS_CONFIG = {
  completed: { icon: CheckCircle2, color: "text-green-500", label: "Ready" },
  processing: { icon: Loader2, color: "text-yellow-500", label: "Processing", spin: true },
  failed: { icon: AlertCircle, color: "text-red-500", label: "Failed" },
  pending: { icon: Clock, color: "text-muted-foreground", label: "Pending" },
};

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between py-3 border-b border-border last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium text-right max-w-[60%]">{value}</span>
    </div>
  );
}

const TABS = ["Overview", "Chunks", "Entities", "Raw Text"] as const;
type Tab = (typeof TABS)[number];

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [chunkPage, setChunkPage] = useState(1);

  const { data: doc, isLoading } = useQuery<DocumentDetail>({
    queryKey: ["document", id],
    queryFn: () => api.get(`/documents/${id}`).then((r) => r.data),
    refetchInterval: (q) => {
      const d = q.state.data as DocumentDetail | undefined;
      return d?.status === "processing" || d?.status === "pending" ? 4000 : false;
    },
  });

  const { data: chunks } = useQuery({
    queryKey: ["chunks", id, chunkPage],
    queryFn: () => api.get(`/documents/${id}/chunks`, { params: { page: chunkPage, page_size: 10 } }).then((r) => r.data),
    enabled: activeTab === "Chunks",
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/documents/${id}`),
    onSuccess: () => {
      toast.success("Document deleted");
      router.push("/documents");
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: () => api.post(`/documents/${id}/reprocess`),
    onSuccess: () => {
      toast.success("Reprocessing started");
      qc.invalidateQueries({ queryKey: ["document", id] });
    },
  });

  const handleDownload = () => {
    window.open(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/documents/${id}/download`, "_blank");
  };

  if (isLoading) {
    return (
      <AppLayout>
        <div className="p-8 animate-pulse">
          <div className="h-8 bg-muted rounded w-64 mb-6" />
          <div className="grid lg:grid-cols-3 gap-6">
            <div className="h-96 bg-muted rounded-xl" />
            <div className="lg:col-span-2 h-96 bg-muted rounded-xl" />
          </div>
        </div>
      </AppLayout>
    );
  }

  if (!doc) {
    return (
      <AppLayout>
        <div className="p-8 text-center">
          <p className="text-muted-foreground">Document not found</p>
          <Link href="/documents" className="text-primary hover:underline text-sm mt-2 inline-block">
            Back to documents
          </Link>
        </div>
      </AppLayout>
    );
  }

  const statusCfg = STATUS_CONFIG[doc.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.pending;
  const entities = (doc.metadata?.entities as Array<{ text: string; label: string; label_human: string; context: string }>) ?? [];

  return (
    <AppLayout>
      <div className="p-8">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
          <Link href="/documents" className="hover:text-foreground transition flex items-center gap-1">
            <ArrowLeft className="w-3.5 h-3.5" />
            Documents
          </Link>
          <ChevronRight className="w-3.5 h-3.5" />
          <span className="text-foreground truncate max-w-xs">{doc.original_filename}</span>
        </div>

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center shrink-0">
              <FileText className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold">{doc.original_filename}</h1>
              <div className="flex items-center gap-3 mt-1.5">
                <span className={cn("flex items-center gap-1.5 text-sm", statusCfg.color)}>
                  <statusCfg.icon className={cn("w-4 h-4", (statusCfg as { spin?: boolean }).spin && "animate-spin")} />
                  {statusCfg.label}
                </span>
                <span className="text-muted-foreground text-xs">v{doc.version}</span>
                {doc.language && (
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Globe className="w-3 h-3" />
                    {doc.language.toUpperCase()}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:bg-accent text-sm transition"
            >
              <Download className="w-4 h-4" />
              Download
            </button>
            <Link
              href={`/copilot?document=${id}`}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition"
            >
              <MessageSquare className="w-4 h-4" />
              Ask Copilot
            </Link>
            {doc.status === "failed" && (
              <button
                onClick={() => reprocessMutation.mutate()}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-yellow-500/30 text-yellow-500 hover:bg-yellow-500/10 text-sm transition"
              >
                <RefreshCw className="w-4 h-4" />
                Retry
              </button>
            )}
            <button
              onClick={() => { if (confirm("Delete this document?")) deleteMutation.mutate(); }}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:bg-destructive/10 hover:text-destructive text-sm transition"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          {[
            { icon: Layers, label: "Chunks", value: doc.chunk_count },
            { icon: BookOpen, label: "Pages", value: doc.page_count },
            { icon: Hash, label: "Entities", value: doc.entity_count },
            { icon: FileText, label: "Size", value: formatBytes(doc.file_size) },
          ].map((s) => (
            <div key={s.label} className="bg-card border border-border rounded-lg p-3 flex items-center gap-3">
              <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center">
                <s.icon className="w-4 h-4 text-primary" />
              </div>
              <div>
                <p className="text-lg font-bold leading-none">{s.value}</p>
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
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="font-semibold mb-4">Document Info</h3>
                <InfoRow label="Filename" value={doc.original_filename} />
                <InfoRow label="MIME Type" value={doc.mime_type} />
                <InfoRow label="File Size" value={formatBytes(doc.file_size)} />
                <InfoRow label="Pages" value={doc.page_count} />
                <InfoRow label="Language" value={doc.language ?? "Unknown"} />
                <InfoRow label="Version" value={`v${doc.version}`} />
                <InfoRow label="Uploaded" value={formatDate(doc.created_at)} />
                <InfoRow label="Category" value={doc.category ?? "—"} />
              </div>
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="font-semibold mb-4">Processing Status</h3>
                <InfoRow label="OCR" value={<span className={cn("capitalize", doc.ocr_status === "completed" ? "text-green-500" : doc.ocr_status === "failed" ? "text-red-500" : "text-yellow-500")}>{doc.ocr_status}</span>} />
                <InfoRow label="Embedding" value={<span className={cn("capitalize", doc.embedding_status === "completed" ? "text-green-500" : doc.embedding_status === "failed" ? "text-red-500" : "text-yellow-500")}>{doc.embedding_status}</span>} />
                <InfoRow label="Chunks" value={doc.chunk_count} />
                <InfoRow label="Entities" value={doc.entity_count} />
                {doc.error_message && (
                  <div className="mt-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-xs text-destructive">
                    {doc.error_message}
                  </div>
                )}
                {doc.tags?.length > 0 && (
                  <div className="mt-4">
                    <p className="text-sm text-muted-foreground mb-2">Tags</p>
                    <div className="flex flex-wrap gap-2">
                      {doc.tags.map((tag) => (
                        <span key={tag} className="flex items-center gap-1 px-2 py-1 bg-primary/10 text-primary rounded text-xs">
                          <Tag className="w-2.5 h-2.5" />
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "Chunks" && (
            <div className="space-y-3">
              {!chunks ? (
                <div className="flex items-center justify-center py-12 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" />Loading chunks…
                </div>
              ) : chunks.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">No chunks yet</div>
              ) : (
                chunks.map((chunk: { id: string; chunk_index: number; page_number: number | null; token_count: number; text: string }) => (
                  <div key={chunk.id} className="bg-card border border-border rounded-lg p-4">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-xs font-mono bg-primary/10 text-primary px-2 py-0.5 rounded">#{chunk.chunk_index}</span>
                      {chunk.page_number && <span className="text-xs text-muted-foreground">Page {chunk.page_number}</span>}
                      <span className="text-xs text-muted-foreground">{chunk.token_count} tokens</span>
                    </div>
                    <p className="text-sm text-foreground/80 leading-relaxed line-clamp-4">{chunk.text}</p>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "Entities" && (
            <div>
              {entities.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">No entities extracted</div>
              ) : (
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {entities.map((ent, i) => (
                    <div key={i} className="bg-card border border-border rounded-lg p-3">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-sm font-medium truncate">{ent.text}</span>
                        <span className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary rounded ml-2 shrink-0">{ent.label_human}</span>
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2">{ent.context}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === "Raw Text" && (
            <div className="bg-card border border-border rounded-xl p-5">
              {doc.extracted_text ? (
                <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap leading-relaxed max-h-[60vh] overflow-auto">
                  {doc.extracted_text}
                </pre>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  {doc.status === "processing" ? "Extracting text…" : "No text extracted"}
                </div>
              )}
            </div>
          )}
        </motion.div>
      </div>
    </AppLayout>
  );
}
