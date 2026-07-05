"use client";

/**
 * apps/web/components/copilot/ConversationSidebar.tsx
 *
 * Left sidebar showing the user's past conversation sessions.
 * Clicking a session loads it back into the chat area.
 * Includes "New conversation" button at the top.
 */

import { useEffect, useState } from "react";
import { getSessions } from "@/lib/api/copilot";
import type { SessionSummary } from "@/lib/types/copilot";

interface Props {
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewConversation: () => void;
  /** Incremented by the parent when a new message is sent, so the list re-fetches. */
  refreshToken: number;
}

function timeAgo(isoString: string | null): string {
  if (!isoString) return "";
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function ConversationSidebar({
  activeSessionId,
  onSelectSession,
  onNewConversation,
  refreshToken,
}: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getSessions()
      .then((data) => { if (!cancelled) { setSessions(data); setLoading(false); } })
      .catch(() => { if (!cancelled) { setError("Failed to load history"); setLoading(false); } });
    return () => { cancelled = true; };
  }, [refreshToken]);

  return (
    <aside
      className="
        w-64 flex-shrink-0 h-full flex flex-col
        border-r border-border bg-card
      "
      aria-label="Conversation history"
    >
      {/* New conversation button */}
      <div className="p-3 border-b border-border">
        <button
          onClick={onNewConversation}
          className="
            w-full flex items-center justify-center gap-2
            px-3 py-2 rounded-lg text-sm font-semibold
            bg-primary text-primary-foreground
            hover:bg-primary/90 active:bg-primary/80
            transition-colors
          "
        >
          <span aria-hidden>+</span> New conversation
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-2">
        {loading && (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            Loading history…
          </div>
        )}

        {error && (
          <div className="px-4 py-3 text-xs text-destructive">{error}</div>
        )}

        {!loading && !error && sessions.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            No conversations yet.
          </div>
        )}

        {sessions.map((session) => {
          const isActive = session.session_id === activeSessionId;
          return (
            <button
              key={session.session_id}
              onClick={() => onSelectSession(session.session_id)}
              className={`
                w-full text-left px-3 py-2.5 rounded-lg mx-1
                transition-colors group
                ${isActive
                  ? "bg-primary/10 border border-primary/20"
                  : "hover:bg-accent border border-transparent"
                }
              `}
              aria-current={isActive ? "page" : undefined}
            >
              {/* Title */}
              <p
                className={`
                  text-sm truncate font-medium
                  ${isActive ? "text-primary" : "text-foreground/80 group-hover:text-foreground"}
                `}
              >
                {session.title ?? "New conversation"}
              </p>

              {/* Meta row */}
              <div className="flex items-center gap-1.5 mt-0.5">
                {session.pinned_asset_tag && (
                  <span
                    className="
                      text-[10px] px-1.5 py-0.5 rounded
                      bg-primary/15 text-primary font-semibold flex-shrink-0
                    "
                    title={`Pinned asset: ${session.pinned_asset_tag}`}
                  >
                    📌 {session.pinned_asset_tag}
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground truncate">
                  {timeAgo(session.last_active_at)}
                </span>
                <span className="text-[10px] text-muted-foreground/60 flex-shrink-0">
                  {session.message_count} msgs
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
