"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";
import {
  LayoutDashboard, FileText, Search, MessageSquare, Factory,
  Settings, LogOut, Zap, ChevronRight, User, Activity, ShieldCheck,
  Brain, History, Users2, Bot,
} from "lucide-react";

const nav = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/documents", icon: FileText, label: "Documents" },
  { href: "/search", icon: Search, label: "Search" },
  { href: "/copilot", icon: MessageSquare, label: "Copilot" },
  // FIX: this link was dropped when the "Knowledge Intelligence" section
  // (knowledgeNav below) was added — the /agents backend routes and pages
  // were never removed, just stopped being linked from the sidebar.
  { href: "/agents", icon: Bot, label: "Agents" },
  { href: "/assets", icon: Factory, label: "Assets" },
];

const adminNav = [
  { href: "/processing", icon: Activity, label: "Processing" },
  { href: "/audit-logs", icon: ShieldCheck, label: "Audit Logs" },
];

const knowledgeNav = [
  { href: "/knowledge", icon: Brain, label: "Knowledge Dashboard" },
  { href: "/time-machine", icon: History, label: "Time Machine" },
  { href: "/shadow-engineer", icon: Users2, label: "Shadow Engineer" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();

  const handleLogout = async () => {
    await logout();
    toast.success("Signed out");
    router.push("/login");
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-card border-r border-border flex flex-col shrink-0">
        {/* Logo */}
        <div className="p-6 border-b border-border">
          <Link href="/dashboard" className="flex items-center gap-3 group">
            <div className="w-8 h-8 indus-gradient rounded-lg flex items-center justify-center group-hover:opacity-90 transition">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="font-bold text-sm leading-none">INDUS MIND</p>
              <p className="text-[10px] text-muted-foreground mt-0.5 leading-none">Industrial AI Platform</p>
            </div>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {nav.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all group",
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                )}
              >
                <item.icon className="w-4 h-4 shrink-0" />
                <span className="flex-1">{item.label}</span>
                {active && <ChevronRight className="w-3 h-3 opacity-50" />}
              </Link>
            );
          })}

          <p className="px-3 pt-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Knowledge Intelligence
          </p>
          {knowledgeNav.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all group",
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                )}
              >
                <item.icon className="w-4 h-4 shrink-0" />
                <span className="flex-1">{item.label}</span>
                {active && <ChevronRight className="w-3 h-3 opacity-50" />}
              </Link>
            );
          })}

          {(user?.role === "admin" || user?.role === "engineer") && (
            <>
              <p className="px-3 pt-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Operations
              </p>
              {adminNav.map((item) => {
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all group",
                      active
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent"
                    )}
                  >
                    <item.icon className="w-4 h-4 shrink-0" />
                    <span className="flex-1">{item.label}</span>
                    {active && <ChevronRight className="w-3 h-3 opacity-50" />}
                  </Link>
                );
              })}
            </>
          )}
        </nav>

        {/* User section */}
        <div className="p-4 border-t border-border space-y-1">
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg">
            <div className="w-7 h-7 bg-primary/20 rounded-full flex items-center justify-center">
              <User className="w-3.5 h-3.5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate">{user?.full_name || "User"}</p>
              <p className="text-[10px] text-muted-foreground truncate capitalize">{user?.role}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <motion.div
          key={pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="h-full"
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
