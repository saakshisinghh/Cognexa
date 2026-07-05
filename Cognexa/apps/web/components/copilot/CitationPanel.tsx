"use client";

/**
 * apps/web/components/copilot/CitationPanel.tsx
 *
 * Shows the cited sources beneath an assistant response.
 * Each citation chip is clickable — navigates to the document detail page
 * at the correct page, matching the "Click citation → jump to PDF page"
 * requirement.
 */

import { useState } from "react";
import type { CitationItem } from "@/lib/types/copilot";

interface Props {
  citations: CitationItem[];
  /** Total number of sources in the response header badge. */
  onOpenDocument?: (documentId: string, pageNumber: number | null) => void;
}

const SOURCE_BADGE_COLORS: Record<string, string> = {
  bm25:   "bg-blue-100 text-blue-700",
  vector: "bg-violet-100 text-violet-700",
  graph:  "bg-teal-100 text-teal-700",
};

function TrustDot({ score }: { score: number }) {
  const color =
    score >= 0.7 ? "bg-emerald-400"
    : score >= 0.4 ? "bg-amber-400"
    : "bg-red-400";
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${color} flex-shrink-0`}
      title={`Trust score: ${(score * 100).toFixed(0)}%`}
      aria-label={`Trust: ${(score * 100).toFixed(0)}%`}
    />
  );
}

export function CitationPanel({ citations, onOpenDocument }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!citations.length) return null;

  const preview = citations.slice(0, 3);
  const rest = citations.slice(3);
  const shown = expanded ? citations : preview;

  return (
    <div className="mt-3">
      {/* Header */}
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Sources
        </span>
        <span className="bg-gray-100 text-gray-600 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
          {citations.length}
        </span>
      </div>

      {/* Citation chips */}
      <div className="space-y-1.5">
        {shown.map((cit, idx) => (
          <button
            key={cit.chunk_id}
            onClick={() => onOpenDocument?.(cit.document_id, cit.page_number)}
            className="
              w-full text-left flex items-start gap-2.5 px-3 py-2
              rounded-lg border border-gray-200 bg-gray-50
              hover:border-blue-300 hover:bg-blue-50
              transition-colors group text-xs
            "
            title={cit.excerpt}
          >
            {/* Citation number */}
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">
              {idx + 1}
            </span>

            <div className="flex-1 min-w-0">
              {/* Title + page */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-semibold text-gray-800 truncate group-hover:text-blue-700">
                  {cit.document_title}
                </span>
                {cit.page_number && (
                  <span className="text-gray-400 flex-shrink-0">p. {cit.page_number}</span>
                )}
                <TrustDot score={cit.trust_score} />
              </div>

              {/* Excerpt */}
              <p className="text-gray-500 mt-0.5 line-clamp-2 leading-relaxed">
                {cit.excerpt}
              </p>

              {/* Source path badges */}
              <div className="flex gap-1 mt-1 flex-wrap">
                {cit.sources.map((src) => (
                  <span
                    key={src}
                    className={`text-[9px] font-semibold px-1.5 py-0.5 rounded uppercase ${SOURCE_BADGE_COLORS[src] ?? "bg-gray-100 text-gray-500"}`}
                  >
                    {src}
                  </span>
                ))}
              </div>
            </div>

            {/* Open icon */}
            <span className="flex-shrink-0 text-gray-300 group-hover:text-blue-500 text-base mt-0.5">↗</span>
          </button>
        ))}
      </div>

      {/* Show more / less toggle */}
      {rest.length > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-xs text-blue-600 hover:underline"
        >
          {expanded ? `▲ Show fewer` : `▼ Show ${rest.length} more source${rest.length > 1 ? "s" : ""}`}
        </button>
      )}
    </div>
  );
}
