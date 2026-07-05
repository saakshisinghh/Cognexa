/**
 * apps/web/app/assets/[id]/graph/page.tsx
 *
 * Purpose
 * -------
 * The "Graph" tab on the Asset 360 view (referenced in the roadmap as
 * "assets/[id]/ tabs: Documents | Entities | Graph[P3] | Incidents |
 * Stats"). Assembles GraphSidebar + GraphExplorer + NodeDetailsPanel
 * into the three-column layout, loads the initial subgraph for this
 * specific asset on mount.
 *
 * This is a NEW route added under the EXISTING apps/web/app/assets/[id]/
 * directory from Phase 1 — it does not touch the existing
 * page.tsx / layout.tsx / other tabs in that folder, only adds a
 * sibling `graph/page.tsx` route.
 *
 * Dependencies
 * ------------
 * - apps/web/components/graph/{GraphExplorer,GraphSidebar,NodeDetailsPanel}.tsx
 * - apps/web/lib/graph/api.ts
 *
 * This file is NEW.
 */

"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { GraphExplorer } from "@/components/graph/GraphExplorer";
import { GraphSidebar } from "@/components/graph/GraphSidebar";
import { NodeDetailsPanel } from "@/components/graph/NodeDetailsPanel";
import {
  GraphNode,
  GraphSubgraphResponse,
  RelationshipType,
  getAssetSubgraph,
} from "@/lib/graph/api";

export default function AssetGraphTabPage() {
  const params = useParams<{ id: string }>();
  const assetId = params.id;

  const [data, setData] = useState<GraphSubgraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [relationshipFilter, setRelationshipFilter] = useState<RelationshipType[] | null>(null);

  const loadGraph = useCallback(() => {
    setLoading(true);
    setError(null);
    getAssetSubgraph(assetId, 1, 100)
      .then(setData)
      .catch((err: any) => setError(err?.message ?? "Failed to load graph"))
      .finally(() => setLoading(false));
  }, [assetId]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  return (
    <div className="flex h-[calc(100vh-180px)] w-full overflow-hidden rounded-lg border border-gray-200">
      <GraphSidebar
        onSearchResultSelect={(node) => setSelectedNode(node)}
        onFilterChange={setRelationshipFilter}
      />
      <div className="flex-1">
        <GraphExplorer
          initialData={data}
          loading={loading}
          error={error}
          onNodeSelect={setSelectedNode}
          onRetry={loadGraph}
          relationshipFilter={relationshipFilter}
        />
      </div>
      <NodeDetailsPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
    </div>
  );
}
