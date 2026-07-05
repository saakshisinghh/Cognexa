/**
 * apps/web/components/graph/GraphExplorer.tsx
 *
 * Purpose
 * -------
 * Core interactive graph visualization using React Flow. Renders nodes
 * color-coded by NodeLabel, supports click-to-expand, and reports
 * selection up to the parent (Asset Graph Tab / standalone Explorer page)
 * via onNodeSelect.
 *
 * Dependencies
 * ------------
 * - reactflow (npm install reactflow)
 * - apps/web/lib/graph/api.ts (Step 8)
 * - apps/web/components/graph/GraphLoadingState.tsx (Step 10)
 * - apps/web/components/graph/GraphErrorState.tsx (Step 10)
 *
 * This file is NEW.
 */

"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";

import {
  GraphSubgraphResponse,
  GraphNode,
  RelationshipType,
  expandNode,
} from "@/lib/graph/api";
import { GraphLoadingState } from "./GraphLoadingState";
import { GraphErrorState } from "./GraphErrorState";

const NODE_COLORS: Record<string, string> = {
  Asset: "#1F4E79",
  Equipment: "#2E75B6",
  Incident: "#C00000",
  Failure: "#E36C0A",
  FailureMode: "#ED7D31",
  Inspection: "#548235",
  Person: "#7030A0",
  Document: "#808080",
  ComplianceRule: "#BF8F00",
  Site: "#264478",
};

function toFlowNode(node: GraphNode, index: number, centerId?: string | null): Node {
  const angle = (index / 8) * 2 * Math.PI;
  const radius = node.id === centerId ? 0 : 220;
  return {
    id: node.id,
    data: {
      label: String(node.properties?.name ?? node.properties?.title ?? node.label),
      raw: node,
    },
    position: {
      x: 400 + radius * Math.cos(angle),
      y: 300 + radius * Math.sin(angle),
    },
    style: {
      background: NODE_COLORS[node.label] ?? "#555",
      color: "#fff",
      border: node.id === centerId ? "3px solid #FFD700" : "1px solid #333",
      borderRadius: 8,
      padding: 10,
      fontSize: 12,
      width: 160,
      textAlign: "center" as const,
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  };
}

function toFlowEdge(edge: { id: string; source: string; target: string; type: string }): Edge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.type,
    animated: edge.type === "CAUSED_BY",
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: "#999" },
    labelStyle: { fontSize: 10, fill: "#666" },
  };
}

interface GraphExplorerProps {
  initialData: GraphSubgraphResponse | null;
  loading: boolean;
  error: string | null;
  onNodeSelect?: (node: GraphNode) => void;
  onRetry?: () => void;
  relationshipFilter?: RelationshipType[] | null;
}

export function GraphExplorer({
  initialData,
  loading,
  error,
  onNodeSelect,
  onRetry,
  relationshipFilter,
}: GraphExplorerProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [expanding, setExpanding] = useState<string | null>(null);
  const [expandError, setExpandError] = useState<string | null>(null);

  useEffect(() => {
    if (!initialData) return;
    setNodes(initialData.nodes.map((n, i) => toFlowNode(n, i, initialData.center_node_id)));
    setEdges(initialData.edges.map(toFlowEdge));
  }, [initialData, setNodes, setEdges]);

  const filteredEdges = useMemo(() => {
    if (!relationshipFilter || relationshipFilter.length === 0) return edges;
    return edges.filter((e) => relationshipFilter.includes(e.type as RelationshipType));
  }, [edges, relationshipFilter]);

  const handleNodeClick = useCallback(
    async (_: React.MouseEvent, node: Node) => {
      const raw: GraphNode = node.data.raw;
      onNodeSelect?.(raw);
    },
    [onNodeSelect]
  );

  const handleNodeDoubleClick = useCallback(
    async (_: React.MouseEvent, node: Node) => {
      setExpanding(node.id);
      setExpandError(null);
      try {
        const result = await expandNode(node.id, relationshipFilter ?? null, 1, 50);
        setNodes((prev) => {
          const existingIds = new Set(prev.map((n) => n.id));
          const newNodes = result.nodes
            .filter((n) => !existingIds.has(n.id))
            .map((n, i) => toFlowNode(n, prev.length + i, node.id));
          return [...prev, ...newNodes];
        });
        setEdges((prev) => {
          const existingIds = new Set(prev.map((e) => e.id));
          const newEdges = result.edges.filter((e) => !existingIds.has(e.id)).map(toFlowEdge);
          return [...prev, ...newEdges];
        });
      } catch (err: any) {
        setExpandError(err?.message ?? "Failed to expand node");
      } finally {
        setExpanding(null);
      }
    },
    [relationshipFilter, setNodes, setEdges]
  );

  if (loading) return <GraphLoadingState />;
  if (error) return <GraphErrorState message={error} onRetry={onRetry} />;
  if (!initialData || initialData.nodes.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-sm text-gray-500">
        No graph data available for this asset yet. It may not have been synced —
        try the &quot;Resync Graph&quot; action from the admin panel.
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      {expanding && (
        <div className="absolute top-2 left-2 z-10 rounded bg-blue-600 px-3 py-1 text-xs text-white shadow">
          Expanding node…
        </div>
      )}
      {expandError && (
        <div className="absolute top-2 left-2 z-10 rounded bg-red-600 px-3 py-1 text-xs text-white shadow">
          {expandError}
        </div>
      )}
      <ReactFlow
        nodes={nodes}
        edges={filteredEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        fitView
        minZoom={0.2}
        maxZoom={2}
      >
        <Background gap={16} />
        <Controls />
        <MiniMap
          nodeColor={(n) => NODE_COLORS[(n.data?.raw as GraphNode)?.label] ?? "#555"}
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
}
