"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import toast from "react-hot-toast";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import { formatRelativeTime, cn } from "@/lib/utils";
import type { Asset, PaginatedResponse } from "@/types";
import {
  Plus, Search, Factory, Trash2, Eye, ChevronLeft,
  ChevronRight, X, Loader2, MapPin, Tag, Activity,
  FileText
} from "lucide-react";

const HEALTH_COLORS: Record<string, string> = {
  healthy: "bg-green-500/10 text-green-500 border-green-500/20",
  warning: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  critical: "bg-red-500/10 text-red-500 border-red-500/20",
  unknown: "bg-muted text-muted-foreground border-border",
};

const assetSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  location: z.string().optional(),
  asset_type: z.string().optional(),
  health_status: z.string().default("unknown"),
  tags: z.string().optional(),
});

type AssetForm = z.infer<typeof assetSchema>;

function CreateAssetModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<AssetForm>({
    resolver: zodResolver(assetSchema),
    defaultValues: { health_status: "unknown" },
  });

  const create = useMutation({
    mutationFn: (data: AssetForm) =>
      api.post("/assets", {
        ...data,
        tags: data.tags ? data.tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
      }).then((r) => r.data),
    onSuccess: () => {
      toast.success("Asset created");
      qc.invalidateQueries({ queryKey: ["assets"] });
      onClose();
    },
    onError: () => toast.error("Failed to create asset"),
  });

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-card border border-border rounded-2xl p-6 w-full max-w-md"
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-semibold text-lg">Create Asset</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-accent rounded-lg transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit((d) => create.mutate(d))} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">Asset Name *</label>
            <input
              {...register("name")}
              className="w-full px-3 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="e.g. Pump P-101"
            />
            {errors.name && <p className="text-xs text-destructive mt-1">{errors.name.message}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">Description</label>
            <textarea
              {...register("description")}
              rows={2}
              className="w-full px-3 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary resize-none"
              placeholder="Brief description of this asset"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1.5">Location</label>
              <input
                {...register("location")}
                className="w-full px-3 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="Unit 3, Bay 7"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Type</label>
              <select
                {...register("asset_type")}
                className="w-full px-3 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">Select type</option>
                <option value="pump">Pump</option>
                <option value="compressor">Compressor</option>
                <option value="turbine">Turbine</option>
                <option value="motor">Motor</option>
                <option value="vessel">Vessel</option>
                <option value="heat_exchanger">Heat Exchanger</option>
                <option value="valve">Valve</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">Health Status</label>
            <select
              {...register("health_status")}
              className="w-full px-3 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="unknown">Unknown</option>
              <option value="healthy">Healthy</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">Tags</label>
            <input
              {...register("tags")}
              className="w-full px-3 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="rotating, critical, zone-a (comma-separated)"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-accent transition">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 text-sm rounded-lg indus-gradient text-white hover:opacity-90 transition flex items-center gap-2 disabled:opacity-50"
            >
              {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Create Asset
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

export default function AssetsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const { data, isLoading } = useQuery<PaginatedResponse<Asset>>({
    queryKey: ["assets", page, search],
    queryFn: () =>
      api.get("/assets", { params: { page, page_size: 20, search: search || undefined } })
        .then((r) => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/assets/${id}`),
    onSuccess: () => {
      toast.success("Asset deleted");
      qc.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: () => toast.error("Failed to delete asset"),
  });

  return (
    <AppLayout>
      <div className="p-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">Assets</h1>
            <p className="text-muted-foreground text-sm mt-1">
              {data?.total ?? 0} industrial assets
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg indus-gradient text-white text-sm font-medium hover:opacity-90 transition"
          >
            <Plus className="w-4 h-4" />
            New Asset
          </button>
        </div>

        {/* Search */}
        <div className="relative mb-6 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search assets…"
            className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        {/* Asset grid */}
        {isLoading ? (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-48 bg-card border border-border rounded-xl animate-pulse" />
            ))}
          </div>
        ) : data?.items.length === 0 ? (
          <div className="text-center py-20">
            <Factory className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
            <p className="font-medium text-muted-foreground">No assets yet</p>
            <p className="text-sm text-muted-foreground mt-1">Create your first industrial asset</p>
            <button
              onClick={() => setShowCreate(true)}
              className="mt-4 px-4 py-2 indus-gradient text-white rounded-lg text-sm hover:opacity-90 transition"
            >
              Create Asset
            </button>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {data?.items.map((asset, i) => (
              <motion.div
                key={asset.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 transition group"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-purple-500/10 rounded-xl flex items-center justify-center">
                      <Factory className="w-5 h-5 text-purple-500" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-sm">{asset.name}</h3>
                      {asset.asset_type && (
                        <p className="text-xs text-muted-foreground capitalize">{asset.asset_type}</p>
                      )}
                    </div>
                  </div>
                  <span className={cn(
                    "px-2 py-1 rounded-full text-[10px] font-medium border capitalize",
                    HEALTH_COLORS[asset.health_status] ?? HEALTH_COLORS.unknown
                  )}>
                    {asset.health_status}
                  </span>
                </div>

                {asset.description && (
                  <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{asset.description}</p>
                )}

                <div className="space-y-1.5 mb-4">
                  {asset.location && (
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <MapPin className="w-3 h-3" />
                      {asset.location}
                    </p>
                  )}
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <FileText className="w-3 h-3" />
                    {asset.document_count} document{asset.document_count !== 1 ? "s" : ""}
                  </p>
                </div>

                {asset.tags?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-4">
                    {asset.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="px-1.5 py-0.5 bg-primary/10 text-primary rounded text-[10px] flex items-center gap-0.5">
                        <Tag className="w-2.5 h-2.5" />
                        {tag}
                      </span>
                    ))}
                    {asset.tags.length > 3 && (
                      <span className="px-1.5 py-0.5 bg-muted text-muted-foreground rounded text-[10px]">
                        +{asset.tags.length - 3}
                      </span>
                    )}
                  </div>
                )}

                <div className="flex items-center justify-between pt-3 border-t border-border">
                  <span className="text-[10px] text-muted-foreground">{formatRelativeTime(asset.updated_at)}</span>
                  <div className="flex items-center gap-1">
                    <Link
                      href={`/assets/${asset.id}`}
                      className="p-1.5 rounded hover:bg-accent transition"
                    >
                      <Eye className="w-3.5 h-3.5 text-muted-foreground" />
                    </Link>
                    <button
                      onClick={() => { if (confirm("Delete this asset?")) deleteMutation.mutate(asset.id); }}
                      className="p-1.5 rounded hover:bg-destructive/10 transition"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-muted-foreground hover:text-destructive transition" />
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-between mt-6">
            <p className="text-sm text-muted-foreground">Page {page} of {data.pages}</p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => p - 1)}
                disabled={page === 1}
                className="p-2 rounded-lg border border-border hover:bg-accent disabled:opacity-40 transition"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page === data.pages}
                className="p-2 rounded-lg border border-border hover:bg-accent disabled:opacity-40 transition"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      <AnimatePresence>
        {showCreate && <CreateAssetModal onClose={() => setShowCreate(false)} />}
      </AnimatePresence>
    </AppLayout>
  );
}
