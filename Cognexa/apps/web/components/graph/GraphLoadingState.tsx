/**
 * apps/web/components/graph/GraphLoadingState.tsx
 *
 * Purpose: skeleton/spinner shown while the initial subgraph fetch is in
 * flight. Kept as its own component so GraphExplorer.tsx stays focused
 * on rendering logic, and so other graph-adjacent views (Sidebar stats,
 * etc.) can reuse the same skeleton.
 *
 * Dependencies: none beyond React + Tailwind (existing project setup).
 * This file is NEW.
 */

"use client";

import React from "react";

export function GraphLoadingState() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-gray-400">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
      <p className="text-sm">Loading knowledge graph…</p>
      <div className="grid grid-cols-3 gap-3 opacity-40">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-12 w-32 animate-pulse rounded-md bg-gray-200" />
        ))}
      </div>
    </div>
  );
}
