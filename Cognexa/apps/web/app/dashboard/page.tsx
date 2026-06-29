"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import Link from "next/link";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import { useAuthStore } from "@/store/auth";
import { formatBytes, formatRelativeTime, getStatusColor, cn } from "@/lib/utils";
import type { DashboardStats } from "@/types";
import {
  FileText, Factory, Users, MessageSquare, HardDrive,
  Clock, CheckCircle2, AlertCircle, Loader2, TrendingUp, ArrowRight
} from "lucide-react";

function StatCard({
  title, value, icon: Icon, color, trend, delay
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  trend?: string;
  delay: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
      className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 transition-all group"
    >
      <div className="flex items-start justify-between mb-4">
        <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", color)}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        {trend && (
          <span className="text-xs text-green-500 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" />
            {trend}
          </span>
        )}
      </div>
      <p className="text-2xl font-bold mb-1">{value}</p>
      <p className="text-sm text-muted-foreground">{title}</p>
    </motion.div>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-card border border-border rounded-xl p-5 animate-pulse">
      <div className="w-10 h-10 bg-muted rounded-lg mb-4" />
      <div className="h-7 bg-muted rounded w-16 mb-2" />
      <div className="h-4 bg-muted rounded w-24" />
    </div>
  );
}

const STATUS_ICONS = {
  completed: <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />,
  processing: <Loader2 className="w-3.5 h-3.5 text-yellow-500 animate-spin" />,
  failed: <AlertCircle className="w-3.5 h-3.5 text-red-500" />,
  pending: <Clock className="w-3.5 h-3.5 text-muted-foreground" />,
};

export default function DashboardPage() {
  const router = useRouter();
  const { isAuthenticated, fetchMe } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }
    fetchMe();
  }, [isAuthenticated, router, fetchMe]);

  const { data: stats, isLoading } = useQuery<DashboardStats>({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.get("/dashboard/stats").then((r) => r.data),
    refetchInterval: 30_000,
    enabled: isAuthenticated,
  });

  return (
    <AppLayout>
      <div className="p-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Platform overview and recent activity
          </p>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {isLoading ? (
            Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)
          ) : (
            <>
              <StatCard title="Total Documents" value={stats?.total_documents ?? 0} icon={FileText} color="bg-indus-600" delay={0} />
              <StatCard title="Assets" value={stats?.total_assets ?? 0} icon={Factory} color="bg-purple-600" delay={0.05} />
              <StatCard title="Users" value={stats?.total_users ?? 0} icon={Users} color="bg-sky-600" delay={0.1} />
              <StatCard title="Conversations" value={stats?.total_conversations ?? 0} icon={MessageSquare} color="bg-emerald-600" delay={0.15} />
              <StatCard title="Processing" value={stats?.documents_processing ?? 0} icon={Loader2} color="bg-yellow-600" delay={0.2} />
              <StatCard title="Completed" value={stats?.documents_completed ?? 0} icon={CheckCircle2} color="bg-green-600" delay={0.25} />
              <StatCard title="Failed" value={stats?.documents_failed ?? 0} icon={AlertCircle} color="bg-red-600" delay={0.3} />
              <StatCard title="Storage Used" value={formatBytes(stats?.storage_used_bytes ?? 0)} icon={HardDrive} color="bg-slate-600" delay={0.35} />
            </>
          )}
        </div>

        {/* Recent activity */}
        <div className="grid lg:grid-cols-2 gap-6">
          {/* Recent uploads */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="bg-card border border-border rounded-xl"
          >
            <div className="p-5 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold">Recent Uploads</h2>
              <Link href="/documents" className="text-xs text-primary hover:underline flex items-center gap-1">
                View all <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="divide-y divide-border">
              {isLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="p-4 flex items-center gap-3 animate-pulse">
                    <div className="w-8 h-8 bg-muted rounded" />
                    <div className="flex-1">
                      <div className="h-3.5 bg-muted rounded w-3/4 mb-2" />
                      <div className="h-3 bg-muted rounded w-1/4" />
                    </div>
                  </div>
                ))
              ) : stats?.recent_uploads.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground text-sm">
                  No documents uploaded yet
                </div>
              ) : (
                stats?.recent_uploads.map((doc) => (
                  <Link key={doc.id} href={`/documents/${doc.id}`} className="p-4 flex items-center gap-3 hover:bg-accent transition group">
                    <div className="w-8 h-8 bg-primary/10 rounded flex items-center justify-center shrink-0">
                      <FileText className="w-4 h-4 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover:text-primary transition">{doc.filename}</p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {STATUS_ICONS[doc.status as keyof typeof STATUS_ICONS]}
                        <span className="text-xs text-muted-foreground capitalize">{doc.status}</span>
                      </div>
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0">{formatRelativeTime(doc.created_at)}</span>
                  </Link>
                ))
              )}
            </div>
          </motion.div>

          {/* Recent conversations */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.45 }}
            className="bg-card border border-border rounded-xl"
          >
            <div className="p-5 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold">Recent Conversations</h2>
              <Link href="/copilot" className="text-xs text-primary hover:underline flex items-center gap-1">
                Open Copilot <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="divide-y divide-border">
              {isLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="p-4 animate-pulse">
                    <div className="h-3.5 bg-muted rounded w-2/3 mb-2" />
                    <div className="h-3 bg-muted rounded w-1/3" />
                  </div>
                ))
              ) : stats?.recent_conversations.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground text-sm">
                  No conversations yet
                </div>
              ) : (
                stats?.recent_conversations.map((c) => (
                  <Link key={c.id} href={`/copilot?conversation=${c.id}`} className="p-4 flex items-center gap-3 hover:bg-accent transition group">
                    <div className="w-8 h-8 bg-emerald-500/10 rounded flex items-center justify-center shrink-0">
                      <MessageSquare className="w-4 h-4 text-emerald-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover:text-primary transition">
                        {c.title || "Untitled conversation"}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">{formatRelativeTime(c.updated_at)}</p>
                    </div>
                  </Link>
                ))
              )}
            </div>
          </motion.div>
        </div>
      </div>
    </AppLayout>
  );
}
