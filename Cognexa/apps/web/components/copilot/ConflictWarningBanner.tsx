"use client";

/**
 * apps/web/components/copilot/ConflictWarningBanner.tsx
 *
 * Amber warning banner displayed below assistant messages that contain
 * detected source conflicts. Shows both conflicting positions side-by-side
 * and encourages the user to verify with the current approved document.
 */

import { useState } from "react";
import type { ConflictFlag } from "@/lib/types/copilot";

interface Props {
  conflicts: ConflictFlag[];
}

const SEVERITY_LABEL: Record<string, string> = {
  minor:    "Minor difference",
  moderate: "Conflicting values",
  major:    "Direct contradiction",
};

export function ConflictWarningBanner({ conflicts }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!conflicts.length) return null;

  return (
    <div
      className="mt-3 rounded-lg border border-amber-300 bg-amber-50 overflow-hidden"
      role="alert"
      aria-live="polite"
    >
      {/* Header bar */}
      <button
        className="
          w-full flex items-center gap-2 px-3 py-2.5
          text-amber-800 text-sm font-semibold text-left
          hover:bg-amber-100 transition-colors
        "
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="text-base" aria-hidden>⚠️</span>
        <span>
          {conflicts.length === 1
            ? "1 source conflict detected"
            : `${conflicts.length} source conflicts detected`}
        </span>
        <span className="ml-auto text-amber-600 text-xs">
          {expanded ? "▲ hide" : "▼ show details"}
        </span>
      </button>

      {/* Expanded conflict cards */}
      {expanded && (
        <div className="px-3 pb-3 space-y-3">
          <p className="text-amber-700 text-xs leading-relaxed">
            The sources below contain conflicting information on the same topic.
            Please verify with the currently approved procedure before acting.
          </p>

          {conflicts.map((flag, i) => (
            <div
              key={flag.chunk_a_id + flag.chunk_b_id + i}
              className="rounded border border-amber-200 bg-white overflow-hidden text-xs"
            >
              {/* Topic header */}
              <div className="flex items-center justify-between px-3 py-1.5 bg-amber-100">
                <span className="font-semibold text-amber-800">
                  {flag.topic.replace(/_/g, " ")}
                </span>
                <span className="text-amber-600 italic">
                  {SEVERITY_LABEL[flag.severity] ?? flag.severity}
                </span>
              </div>

              {/* Side-by-side excerpts */}
              <div className="grid grid-cols-2 divide-x divide-amber-100">
                <div className="p-2.5">
                  <p className="font-semibold text-gray-500 mb-1 truncate" title={flag.chunk_a_document_title}>
                    {flag.chunk_a_document_title}
                  </p>
                  <p className="text-gray-700 leading-relaxed line-clamp-4">
                    &ldquo;{flag.chunk_a_excerpt}&rdquo;
                  </p>
                </div>
                <div className="p-2.5">
                  <p className="font-semibold text-gray-500 mb-1 truncate" title={flag.chunk_b_document_title}>
                    {flag.chunk_b_document_title}
                  </p>
                  <p className="text-gray-700 leading-relaxed line-clamp-4">
                    &ldquo;{flag.chunk_b_excerpt}&rdquo;
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
