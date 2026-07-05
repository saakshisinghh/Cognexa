/**
 * apps/web/components/graph/NodeDetailsPanel.tsx
 *
 * Purpose
 * -------
 * Side panel showing full properties of the currently selected graph
 * node, plus a contextual "View similar assets" action when the node
 * is an Asset (calls getSimilarAssets from Step 8's api client).
 *
 * Dependencies
 * ------------
 * - apps/web/lib/graph/api.ts (GraphNode, getSimilarAssets, SimilarityResult)
 *
 * This file is NEW.
 */

"use client";

import React, { useEffect, useState } from "react";
import { GraphNode, SimilarityResult, getSimilarAssets } from "@/lib/graph/api";

interface NodeDetailsPanelProps {
  node: GraphNode | null;
  onClose: () => void;
}

export function NodeDetailsPanel({ node, onClose }: NodeDetailsPanelProps) {
  const [similar, setSimilar] = useState<SimilarityResult[]>([]);
  const [loadingSimilar, setLoadingSimilar] = useState(false);

  useEffect(() => {
    setSimilar([]);
    if (!node || node.label !== "Asset") return;
    const assetId = node.properties?.asset_id as string | undefined;
    if (!assetId) return;

    setLoadingSimilar(true);
    getSimilarAssets(assetId, 5)
      .then(setSimilar)
      .catch(() => setSimilar([]))
      .finally(() => setLoadingSimilar(false));
  }, [node]);

  if (!node) {
    return (
      <div className="flex h-full w-72 items-center justify-center border-l border-gray-200 p-4 text-xs text-gray-400">
        Select a node to view details
      </div>
    );
  }

  return (
    <div className="flex h-full w-72 flex-col border-l border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-100 p-3">
        <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
          {node.label}
        </span>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600" aria-label="Close panel">
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        <h3 className="mb-2 text-sm font-semibold text-gray-800">
          {String(node.properties?.name ?? node.properties?.title ?? "Untitled")}
        </h3>
        <dl className="space-y-2">
          {Object.entries(node.properties)
            .filter(([key]) => !["name", "title"].includes(key))
            .map(([key, value]) => (
              <div key={key} className="text-xs">
                <dt className="font-medium text-gray-500">{key}</dt>
                <dd className="text-gray-800 break-words">{String(value)}</dd>
              </div>
            ))}
        </dl>

        {node.label === "Asset" && (
          <div className="mt-4 border-t border-gray-100 pt-3">
            <h4 className="mb-2 text-xs font-semibold text-gray-600">Similar Assets</h4>
            {loadingSimilar && <p className="text-xs text-gray-400">Loading…</p>}
            {!loadingSimilar && similar.length === 0 && (
              <p className="text-xs text-gray-400">No similarity data computed yet.</p>
            )}
            <ul className="space-y-1.5">
              {similar.map((s) => (
                <li key={s.node_id} className="flex items-center justify-between text-xs">
                  <span className="truncate">{String(s.properties?.name ?? s.node_id)}</span>
                  <span className="ml-2 shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-gray-600">
                    {(s.similarity_score * 100).toFixed(0)}%
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
