"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";
import {
  LayoutDashboard, FileText, Search, MessageSquare, Factory,
  Settings, LogOut, Zap, ChevronRight, User, Activity, ShieldCheck, X, Bot
} from "lucide-react";

const nav = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/documents", icon: FileText, label: "Documents" },
  { href: "/search", icon: Search, label: "Search" },
  { href: "/copilot", icon: MessageSquare, label: "Copilot" },
  { href: "/agents", icon: Bot, label: "Agents" },
  { href: "/assets", icon: Factory, label: "Assets" },
];

// FIX (issues #6 / #13 — "Roles" / "Frontend Polish"): Processing requires
// require_engineer_or_admin on the backend (apps/api/routers/jobs.py), but
// Audit Logs requires require_admin only (apps/api/routers/audit.py). This
// component previously showed BOTH links to admin AND engineer, so an
// Engineer clicking "Audit Logs" would hit a 403 the UI never explained.
// Split into an "engineer or admin" section and an admin-only section so
// the nav a user sees always matches what they're actually allowed to open.
const engineerOrAdminNav = [
  { href: "/processing", icon: Activity, label: "Processing" },
];

const adminOnlyNav = [
  { href: "/audit-logs", icon: ShieldCheck, label: "Audit Logs" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  const handleLogout = async () => {
    setShowLogoutConfirm(false);
    await logout();
    toast.success("Signed out");
    router.push("/login");
  };

  const isEngineerOrAdmin = user?.role === "admin" || user?.role === "engineer";
  const isAdmin = user?.role === "admin";

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

          {(isEngineerOrAdmin || isAdmin) && (
            <>
              <p className="px-3 pt-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Operations
              </p>
              {isEngineerOrAdmin &&
                engineerOrAdminNav.map((item) => {
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
              {isAdmin &&
                adminOnlyNav.map((item) => {
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
            onClick={() => setShowLogoutConfirm(true)}
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

      {/* FIX (issue #6 — "Logout confirmation" missing): sign-out previously
          fired immediately on click with no way to back out of an accidental
          click. Added a lightweight confirmation dialog. */}
      <AnimatePresence>
        {showLogoutConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
            onClick={() => setShowLogoutConfirm(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between mb-2">
                <h2 className="text-base font-semibold">Sign out?</h2>
                <button
                  onClick={() => setShowLogoutConfirm(false)}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Close"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <p className="text-sm text-muted-foreground mb-6">
                You'll need to sign in again to access your documents, assets, and conversations.
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowLogoutConfirm(false)}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:bg-accent transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleLogout}
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-destructive text-destructive-foreground hover:opacity-90 transition"
                >
                  Sign out
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
