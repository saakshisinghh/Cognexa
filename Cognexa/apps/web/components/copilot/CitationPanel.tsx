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
  bm25:   "bg-blue-500/15 text-blue-400",
  vector: "bg-violet-500/15 text-violet-400",
  graph:  "bg-teal-500/15 text-teal-400",
};

function TrustDot({ score }: { score: number }) {
  const color =
    score >= 0.7 ? "bg-emerald-500"
    : score >= 0.4 ? "bg-amber-500"
    : "bg-red-500";
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
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Sources
        </span>
        <span className="bg-accent text-muted-foreground text-[10px] font-bold px-1.5 py-0.5 rounded-full">
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
              rounded-lg border border-border bg-accent/40
              hover:border-primary/40 hover:bg-primary/10
              transition-colors group text-xs
            "
            title={cit.excerpt}
          >
            {/* Citation number */}
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center">
              {idx + 1}
            </span>

            <div className="flex-1 min-w-0">
              {/* Title + page */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-semibold text-foreground truncate group-hover:text-primary">
                  {cit.document_title}
                </span>
                {cit.page_number && (
                  <span className="text-muted-foreground flex-shrink-0">p. {cit.page_number}</span>
                )}
                <TrustDot score={cit.trust_score} />
              </div>

              {/* Excerpt */}
              <p className="text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">
                {cit.excerpt}
              </p>

              {/* Source path badges */}
              <div className="flex gap-1 mt-1 flex-wrap">
                {cit.sources.map((src) => (
                  <span
                    key={src}
                    className={`text-[9px] font-semibold px-1.5 py-0.5 rounded uppercase ${SOURCE_BADGE_COLORS[src] ?? "bg-accent text-muted-foreground"}`}
                  >
                    {src}
                  </span>
                ))}
              </div>
            </div>

            {/* Open icon */}
            <span className="flex-shrink-0 text-muted-foreground/50 group-hover:text-primary text-base mt-0.5">↗</span>
          </button>
        ))}
      </div>

      {/* Show more / less toggle */}
      {rest.length > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-xs text-primary hover:underline"
        >
          {expanded ? `▲ Show fewer` : `▼ Show ${rest.length} more source${rest.length > 1 ? "s" : ""}`}
        </button>
      )}
    </div>
  );
}
