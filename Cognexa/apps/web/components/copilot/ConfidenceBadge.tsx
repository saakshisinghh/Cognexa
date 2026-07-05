"use client";

/**
 * apps/web/components/copilot/ConfidenceBadge.tsx
 *
 * Displays the confidence level (HIGH / MEDIUM / LOW) with color coding
 * and an explanation shown on hover. Appears below every assistant message.
 */

import type { ConfidencePayload } from "@/lib/types/copilot";

const LEVEL_STYLES: Record<string, { bg: string; text: string; dot: string; label: string }> = {
  high:   { bg: "bg-emerald-50",  text: "text-emerald-700", dot: "bg-emerald-500", label: "HIGH" },
  medium: { bg: "bg-amber-50",    text: "text-amber-700",   dot: "bg-amber-400",   label: "MEDIUM" },
  low:    { bg: "bg-red-50",      text: "text-red-700",     dot: "bg-red-400",     label: "LOW" },
};

interface Props {
  confidence: ConfidencePayload;
}

export function ConfidenceBadge({ confidence }: Props) {
  const style = LEVEL_STYLES[confidence.level] ?? LEVEL_STYLES.low;

  return (
    <div className="group relative inline-flex items-center gap-1.5 mt-2">
      <span
        className={`
          inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold
          cursor-default select-none border
          ${style.bg} ${style.text}
          border-current border-opacity-20
        `}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} aria-hidden />
        {style.label} CONFIDENCE
        <span className="opacity-50 ml-0.5 text-[10px]">
          {Math.round(confidence.score * 100)}%
        </span>
      </span>

      {/* Tooltip — shown on hover */}
      <div
        className="
          pointer-events-none absolute bottom-full left-0 mb-2 w-72
          bg-gray-900 text-gray-100 text-xs rounded-lg px-3 py-2 shadow-xl
          opacity-0 group-hover:opacity-100 transition-opacity duration-150
          z-50 leading-relaxed
        "
        role="tooltip"
      >
        {confidence.explanation}
        <div
          className="absolute top-full left-4 border-4 border-transparent border-t-gray-900"
          aria-hidden
        />
      </div>
    </div>
  );
}
