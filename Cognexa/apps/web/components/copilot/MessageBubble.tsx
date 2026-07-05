"use client";

/**
 * apps/web/components/copilot/MessageBubble.tsx
 *
 * Renders a single chat message. Handles:
 *   - User messages (right-aligned, blue)
 *   - Assistant messages with streaming content (left-aligned, white card)
 *   - Streaming indicator (animated dots) while content is arriving
 *   - Post-stream confidence badge, citations, conflict banner
 *   - Error state
 *   - Thumbs up / down feedback (calls onFeedback callback)
 */

import { useState } from "react";
import type { ChatMessage } from "@/lib/types/copilot";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { CitationPanel } from "./CitationPanel";
import { ConflictWarningBanner } from "./ConflictWarningBanner";

interface Props {
  message: ChatMessage;
  onFeedback?: (messageId: string, feedback: "positive" | "negative") => void;
  onOpenDocument?: (documentId: string, pageNumber: number | null) => void;
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-label="Assistant is typing">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </span>
  );
}

export function MessageBubble({ message, onFeedback, onOpenDocument }: Props) {
  const [feedback, setFeedback] = useState<"positive" | "negative" | null>(null);
  const isUser = message.role === "user";

  function handleFeedback(value: "positive" | "negative") {
    if (feedback) return; // already submitted
    setFeedback(value);
    onFeedback?.(message.id, value);
  }

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div
          className="
            max-w-[75%] px-4 py-2.5 rounded-2xl rounded-tr-sm
            bg-blue-600 text-white text-sm leading-relaxed
          "
        >
          {message.content}
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex justify-start mb-4">
      {/* Avatar */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xs font-bold mr-3 mt-0.5">
        IM
      </div>

      <div className="flex-1 max-w-[85%]">
        {/* Message card */}
        <div
          className={`
            px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed
            ${message.hasError
              ? "bg-red-50 border border-red-200 text-red-700"
              : "bg-white border border-gray-200 text-gray-800 shadow-sm"
            }
          `}
        >
          {message.hasError ? (
            <div className="flex items-center gap-2">
              <span>⚠️</span>
              <span>{message.errorMessage ?? "An error occurred."}</span>
            </div>
          ) : message.isStreaming && !message.content ? (
            <TypingDots />
          ) : (
            <>
              {/* Content — whitespace preserved for multi-line answers */}
              <div className="whitespace-pre-wrap break-words">{message.content}</div>
              {message.isStreaming && (
                <span className="inline-block w-0.5 h-4 bg-gray-400 animate-pulse ml-0.5 align-text-bottom" />
              )}
            </>
          )}
        </div>

        {/* Post-stream metadata — only shown once streaming is done */}
        {!message.isStreaming && !message.hasError && (
          <>
            {/* Confidence badge */}
            {message.confidence && (
              <ConfidenceBadge confidence={message.confidence} />
            )}

            {/* Conflict warning */}
            {message.conflicts && message.conflicts.length > 0 && (
              <ConflictWarningBanner conflicts={message.conflicts} />
            )}

            {/* Citations */}
            {message.citations && message.citations.length > 0 && (
              <CitationPanel
                citations={message.citations}
                onOpenDocument={onOpenDocument}
              />
            )}

            {/* Feedback buttons */}
            {message.content && (
              <div className="flex items-center gap-2 mt-2.5">
                <span className="text-[10px] text-gray-400">Was this helpful?</span>
                <button
                  onClick={() => handleFeedback("positive")}
                  disabled={!!feedback}
                  className={`
                    text-sm px-2 py-0.5 rounded transition-colors
                    ${feedback === "positive"
                      ? "text-emerald-600 bg-emerald-50"
                      : "text-gray-400 hover:text-emerald-600 hover:bg-emerald-50"
                    }
                    disabled:cursor-default
                  `}
                  title="Helpful"
                  aria-label="Mark as helpful"
                >
                  👍
                </button>
                <button
                  onClick={() => handleFeedback("negative")}
                  disabled={!!feedback}
                  className={`
                    text-sm px-2 py-0.5 rounded transition-colors
                    ${feedback === "negative"
                      ? "text-red-600 bg-red-50"
                      : "text-gray-400 hover:text-red-600 hover:bg-red-50"
                    }
                    disabled:cursor-default
                  `}
                  title="Not helpful"
                  aria-label="Mark as not helpful"
                >
                  👎
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
