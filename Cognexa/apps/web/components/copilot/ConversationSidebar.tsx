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
        border-r border-gray-200 bg-gray-50
      "
      aria-label="Conversation history"
    >
      {/* New conversation button */}
      <div className="p-3 border-b border-gray-200">
        <button
          onClick={onNewConversation}
          className="
            w-full flex items-center justify-center gap-2
            px-3 py-2 rounded-lg text-sm font-semibold
            bg-indigo-600 text-white
            hover:bg-indigo-700 active:bg-indigo-800
            transition-colors
          "
        >
          <span aria-hidden>+</span> New conversation
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-2">
        {loading && (
          <div className="px-4 py-6 text-center text-sm text-gray-400">
            Loading history…
          </div>
        )}

        {error && (
          <div className="px-4 py-3 text-xs text-red-500">{error}</div>
        )}

        {!loading && !error && sessions.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-gray-400">
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
                  ? "bg-indigo-100 border border-indigo-200"
                  : "hover:bg-gray-100 border border-transparent"
                }
              `}
              aria-current={isActive ? "page" : undefined}
            >
              {/* Title */}
              <p
                className={`
                  text-sm truncate font-medium
                  ${isActive ? "text-indigo-800" : "text-gray-700 group-hover:text-gray-900"}
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
                      bg-blue-100 text-blue-700 font-semibold flex-shrink-0
                    "
                    title={`Pinned asset: ${session.pinned_asset_tag}`}
                  >
                    📌 {session.pinned_asset_tag}
                  </span>
                )}
                <span className="text-[10px] text-gray-400 truncate">
                  {timeAgo(session.last_active_at)}
                </span>
                <span className="text-[10px] text-gray-300 flex-shrink-0">
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
