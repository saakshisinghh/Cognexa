"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import toast from "react-hot-toast";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import { formatBytes, formatRelativeTime, cn } from "@/lib/utils";
import type { Document, PaginatedResponse } from "@/types";
import {
  Upload, Search, FileText, Trash2, RefreshCw, Filter,
  CheckCircle2, AlertCircle, Loader2, Clock, Eye, Tag,
  ChevronLeft, ChevronRight, X, FolderOpen, Plus
} from "lucide-react";

const STATUS_CONFIG = {
  completed: { icon: CheckCircle2, color: "text-green-500", bg: "bg-green-500/10", label: "Ready" },
  processing: { icon: Loader2, color: "text-yellow-500", bg: "bg-yellow-500/10", label: "Processing", spin: true },
  failed: { icon: AlertCircle, color: "text-red-500", bg: "bg-red-500/10", label: "Failed" },
  pending: { icon: Clock, color: "text-muted-foreground", bg: "bg-muted", label: "Pending" },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.pending;
  return (
    <span className={cn("flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium", cfg.color, cfg.bg)}>
      <cfg.icon className={cn("w-3 h-3", (cfg as { spin?: boolean }).spin && "animate-spin")} />
      {cfg.label}
    </span>
  );
}

export default function DocumentsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});

  const { data, isLoading } = useQuery<PaginatedResponse<Document>>({
    queryKey: ["documents", page, search, statusFilter],
    queryFn: () =>
      api.get("/documents", {
        params: { page, page_size: 20, search: search || undefined, status: statusFilter || undefined },
      }).then((r) => r.data),
    refetchInterval: 10_000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/documents/${id}`),
    onSuccess: () => {
      toast.success("Document deleted");
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: () => toast.error("Failed to delete document"),
  });

  const reprocessMutation = useMutation({
    mutationFn: (id: string) => api.post(`/documents/${id}/reprocess`),
    onSuccess: () => {
      toast.success("Reprocessing started");
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const uploadFiles = useCallback(async (files: File[]) => {
    setUploading(true);
    const results = await Promise.allSettled(
      files.map(async (file) => {
        const formData = new FormData();
        formData.append("file", file);
        try {
          await api.post("/documents/upload", formData, {
            headers: { "Content-Type": "multipart/form-data" },
            onUploadProgress: (e) => {
              if (e.total) {
                setUploadProgress((p) => ({ ...p, [file.name]: Math.round((e.loaded / e.total!) * 100) }));
              }
            },
          });
          return { name: file.name, ok: true };
        } catch {
          return { name: file.name, ok: false };
        }
      })
    );
    const ok = results.filter((r) => r.status === "fulfilled" && (r.value as { ok: boolean }).ok).length;
    const fail = files.length - ok;
    if (ok > 0) toast.success(`${ok} file${ok > 1 ? "s" : ""} uploaded successfully`);
    if (fail > 0) toast.error(`${fail} file${fail > 1 ? "s" : ""} failed to upload`);
    setUploadProgress({});
    setUploading(false);
    qc.invalidateQueries({ queryKey: ["documents"] });
  }, [qc]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: uploadFiles,
    accept: {
      "application/pdf": [".pdf"],
      "image/*": [".png", ".jpg", ".jpeg", ".tiff", ".webp"],
      "text/plain": [".txt"],
    },
    maxSize: 100 * 1024 * 1024,
    multiple: true,
  });

  return (
    <AppLayout>
      <div className="p-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">Documents</h1>
            <p className="text-muted-foreground text-sm mt-1">
              {data?.total ?? 0} documents total
            </p>
          </div>
        </div>

        {/* Drop zone */}
        <div
          {...getRootProps()}
          className={cn(
            "border-2 border-dashed rounded-xl p-8 mb-6 text-center cursor-pointer transition-all",
            isDragActive ? "border-primary bg-primary/5 scale-[1.01]" : "border-border hover:border-primary/50 hover:bg-accent/50"
          )}
        >
          <input {...getInputProps()} />
          <Upload className={cn("w-10 h-10 mx-auto mb-3", isDragActive ? "text-primary" : "text-muted-foreground")} />
          <p className="font-medium text-sm">
            {isDragActive ? "Drop files here…" : "Drag & drop files, or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">PDF, images, TXT · Max 100MB per file</p>
        </div>

        {/* Upload progress */}
        <AnimatePresence>
          {Object.keys(uploadProgress).length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-4 space-y-2"
            >
              {Object.entries(uploadProgress).map(([name, pct]) => (
                <div key={name} className="bg-card border border-border rounded-lg p-3">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="truncate">{name}</span>
                    <span className="text-primary font-medium">{pct}%</span>
                  </div>
                  <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-primary rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Filters */}
        <div className="flex gap-3 mb-6">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder="Search documents…"
              className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="px-3 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">All status</option>
            <option value="completed">Ready</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
            <option value="pending">Pending</option>
          </select>
        </div>

        {/* Document list */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 px-5 py-3 border-b border-border bg-muted/30 text-xs font-medium text-muted-foreground">
            <span>Document</span>
            <span>Status</span>
            <span>Chunks</span>
            <span>Size</span>
            <span>Actions</span>
          </div>

          {isLoading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 px-5 py-4 border-b border-border animate-pulse">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-muted rounded" />
                  <div>
                    <div className="h-3.5 bg-muted rounded w-48 mb-1.5" />
                    <div className="h-3 bg-muted rounded w-24" />
                  </div>
                </div>
                <div className="h-6 bg-muted rounded w-20" />
                <div className="h-6 bg-muted rounded w-12" />
                <div className="h-6 bg-muted rounded w-14" />
                <div className="h-6 bg-muted rounded w-16" />
              </div>
            ))
          ) : data?.items.length === 0 ? (
            <div className="p-12 text-center">
              <FolderOpen className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
              <p className="font-medium text-muted-foreground">No documents yet</p>
              <p className="text-sm text-muted-foreground mt-1">Upload your first document above</p>
            </div>
          ) : (
            data?.items.map((doc) => (
              <motion.div
                key={doc.id}
                layout
                className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 items-center px-5 py-4 border-b border-border hover:bg-accent/30 transition"
              >
                <Link href={`/documents/${doc.id}`} className="flex items-center gap-3 min-w-0 group">
                  <div className="w-8 h-8 bg-primary/10 rounded flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate group-hover:text-primary transition">
                      {doc.original_filename}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatRelativeTime(doc.created_at)}
                      {doc.tags?.length > 0 && (
                        <span className="ml-2 inline-flex items-center gap-0.5">
                          <Tag className="w-2.5 h-2.5" />
                          {doc.tags.slice(0, 2).join(", ")}
                        </span>
                      )}
                    </p>
                  </div>
                </Link>
                <StatusBadge status={doc.status} />
                <span className="text-sm text-center">{doc.chunk_count}</span>
                <span className="text-sm text-muted-foreground">{formatBytes(doc.file_size)}</span>
                <div className="flex items-center gap-1">
                  <Link
                    href={`/documents/${doc.id}`}
                    className="p-1.5 rounded hover:bg-accent transition"
                    title="View"
                  >
                    <Eye className="w-3.5 h-3.5 text-muted-foreground" />
                  </Link>
                  {doc.status === "failed" && (
                    <button
                      onClick={() => reprocessMutation.mutate(doc.id)}
                      className="p-1.5 rounded hover:bg-accent transition"
                      title="Reprocess"
                    >
                      <RefreshCw className="w-3.5 h-3.5 text-yellow-500" />
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (confirm("Delete this document?")) deleteMutation.mutate(doc.id);
                    }}
                    className="p-1.5 rounded hover:bg-destructive/10 transition"
                    title="Delete"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-muted-foreground hover:text-destructive transition" />
                  </button>
                </div>
              </motion.div>
            ))
          )}
        </div>

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Page {page} of {data.pages}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => p - 1)}
                disabled={page === 1}
                className="p-2 rounded-lg border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page === data.pages}
                className="p-2 rounded-lg border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
