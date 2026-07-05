"use client";

/**
 * apps/web/components/copilot/QueryInputBar.tsx
 *
 * Bottom-pinned query input for the copilot.
 * Features:
 *   - Auto-resizing textarea (grows with content, max 6 lines)
 *   - Enter to send (Shift+Enter for newline)
 *   - Disabled + loading state while a response is streaming
 *   - Character counter when approaching the 2000-char limit
 */

import { useRef, useEffect, KeyboardEvent, ChangeEvent } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
}

const MAX_CHARS = 2000;

export function QueryInputBar({
  value,
  onChange,
  onSubmit,
  isStreaming,
  disabled = false,
  placeholder = "Ask anything about your industrial assets, incidents, or procedures…",
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea height
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    // Cap at ~6 lines (each ~24px)
    el.style.height = Math.min(el.scrollHeight, 144) + "px";
  }, [value]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSubmit();
  }

  function handleChange(e: ChangeEvent<HTMLTextAreaElement>) {
    if (e.target.value.length <= MAX_CHARS) {
      onChange(e.target.value);
    }
  }

  const charsLeft = MAX_CHARS - value.length;
  const showCounter = charsLeft < 200;
  const isEffectivelyDisabled = disabled || isStreaming;

  return (
    <div
      className="
        flex flex-col gap-1 px-4 py-3
        border-t border-border bg-card
      "
    >
      <div
        className={`
          flex items-end gap-2 rounded-xl border px-3 py-2
          transition-colors
          ${isEffectivelyDisabled
            ? "border-border bg-muted/30"
            : "border-border bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20"
          }
        `}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={isEffectivelyDisabled}
          placeholder={isStreaming ? "Waiting for response…" : placeholder}
          aria-label="Type your question"
          aria-multiline="true"
          className="
            flex-1 resize-none bg-transparent text-sm leading-relaxed
            text-foreground placeholder-muted-foreground
            focus:outline-none
            disabled:text-muted-foreground disabled:cursor-not-allowed
            max-h-36 overflow-y-auto
          "
        />

        {/* Send / Loading button */}
        <button
          onClick={handleSubmit}
          disabled={isEffectivelyDisabled || !value.trim()}
          aria-label={isStreaming ? "Waiting…" : "Send message"}
          className="
            flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center
            transition-colors
            bg-primary text-primary-foreground
            hover:bg-primary/90 active:bg-primary/80
            disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed
          "
        >
          {isStreaming ? (
            <span
              className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"
              aria-hidden
            />
          ) : (
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden>
              <path d="M3.105 2.289a.75.75 0 00-.826.95l1.903 6.932H9.75a.75.75 0 010 1.5H4.182l-1.903 6.932a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
            </svg>
          )}
        </button>
      </div>

      {/* Helpers row */}
      <div className="flex items-center justify-between px-1">
        <span className="text-[10px] text-muted-foreground">
          Enter to send · Shift+Enter for newline
        </span>
        {showCounter && (
          <span
            className={`text-[10px] ${charsLeft < 50 ? "text-destructive font-semibold" : "text-muted-foreground"}`}
          >
            {charsLeft} left
          </span>
        )}
      </div>
    </div>
  );
}
