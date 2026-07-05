/**
 * apps/web/components/graph/GraphErrorState.tsx
 *
 * Purpose: unified error display for graph fetch/expand failures,
 * distinguishing "Neo4j unavailable" (infra issue, show retry) from
 * "not found" (data issue, show guidance) based on message content.
 *
 * Dependencies: none beyond React + Tailwind.
 * This file is NEW.
 */

"use client";

import React from "react";

interface GraphErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function GraphErrorState({ message, onRetry }: GraphErrorStateProps) {
  const isServiceDown =
    message.toLowerCase().includes("unavailable") || message.toLowerCase().includes("503");

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-center px-6">
      <div className="text-4xl">{isServiceDown ? "🔌" : "⚠️"}</div>
      <p className="text-sm font-medium text-gray-700">
        {isServiceDown ? "Graph service is currently unavailable" : "Couldn't load the graph"}
      </p>
      <p className="max-w-sm text-xs text-gray-500">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded-md bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
        >
          Retry
        </button>
      )}
    </div>
  );
}
