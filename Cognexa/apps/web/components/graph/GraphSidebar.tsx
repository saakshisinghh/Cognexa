/**
 * apps/web/components/graph/GraphSidebar.tsx
 *
 * Purpose
 * -------
 * Left sidebar for the Graph Explorer: "Search Asset" box (debounced),
 * relationship-type filter checkboxes, and the Graph Statistics summary.
 * Combines the 4 separate roadmap items (Sidebar, Filters, Search,
 * Statistics) into one cohesive panel component, since in the actual UI
 * they share state and render as one visual column.
 *
 * Dependencies
 * ------------
 * - apps/web/lib/graph/api.ts (searchGraph, getGraphStats, RelationshipType)
 *
 * This file is NEW.
 */

"use client";

import React, { useEffect, useState } from "react";
import {
  GraphNode,
  RelationshipType,
  GraphStatsResponse,
  searchGraph,
  getGraphStats,
} from "@/lib/graph/api";

const ALL_RELATIONSHIP_TYPES: RelationshipType[] = [
  "PART_OF",
  "LOCATED_AT",
  "CAUSED_BY",
  "HAS_FAILURE_MODE",
  "INSPECTED_BY",
  "REPORTED_IN",
  "INVOLVES",
  "AFFECTS",
  "SIMILAR_TO",
  "SUBJECT_TO",
  "AUTHORED_BY",
];

interface GraphSidebarProps {
  onSearchResultSelect: (node: GraphNode) => void;
  onFilterChange: (selected: RelationshipType[] | null) => void;
}

export function GraphSidebar({ onSearchResultSelect, onFilterChange }: GraphSidebarProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GraphNode[]>([]);
  const [searching, setSearching] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Set<RelationshipType>>(
    new Set(ALL_RELATIONSHIP_TYPES)
  );
  const [stats, setStats] = useState<GraphStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  // Debounced search
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    const handle = setTimeout(() => {
      searchGraph(query, null, 10)
        .then((res) => setResults(res.results))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    getGraphStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, []);

  const toggleFilter = (type: RelationshipType) => {
    const next = new Set(activeFilters);
    next.has(type) ? next.delete(type) : next.add(type);
    setActiveFilters(next);
    onFilterChange(next.size === ALL_RELATIONSHIP_TYPES.length ? null : Array.from(next));
  };

  return (
    <div className="flex h-full w-64 flex-col gap-4 overflow-y-auto border-r border-gray-200 bg-gray-50 p-3">
      {/* Search Asset */}
      <div>
        <label className="mb-1 block text-xs font-semibold text-gray-600">Search Graph</label>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search assets, incidents…"
          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
        />
        {searching && <p className="mt-1 text-xs text-gray-400">Searching…</p>}
        {results.length > 0 && (
          <ul className="mt-1 max-h-48 overflow-y-auto rounded border border-gray-200 bg-white">
            {results.map((r) => (
              <li
                key={r.id}
                onClick={() => onSearchResultSelect(r)}
                className="cursor-pointer px-2 py-1.5 text-xs hover:bg-blue-50"
              >
                <span className="font-medium">{String(r.properties?.name ?? r.properties?.title)}</span>
                <span className="ml-1 text-gray-400">({r.label})</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Relationship Filters */}
      <div>
        <label className="mb-1 block text-xs font-semibold text-gray-600">Relationship Filters</label>
        <div className="flex flex-col gap-1">
          {ALL_RELATIONSHIP_TYPES.map((type) => (
            <label key={type} className="flex items-center gap-1.5 text-xs text-gray-700">
              <input
                type="checkbox"
                checked={activeFilters.has(type)}
                onChange={() => toggleFilter(type)}
                className="h-3 w-3"
              />
              {type}
            </label>
          ))}
        </div>
      </div>

      {/* Graph Statistics */}
      <div>
        <label className="mb-1 block text-xs font-semibold text-gray-600">Graph Statistics</label>
        {statsLoading && <p className="text-xs text-gray-400">Loading stats…</p>}
        {!statsLoading && !stats && <p className="text-xs text-red-500">Stats unavailable</p>}
        {stats && (
          <div className="space-y-1 rounded border border-gray-200 bg-white p-2 text-xs">
            <div className="flex justify-between font-medium">
              <span>Total Nodes</span>
              <span>{stats.total_nodes}</span>
            </div>
            <div className="flex justify-between font-medium">
              <span>Total Relationships</span>
              <span>{stats.total_relationships}</span>
            </div>
            <hr className="my-1 border-gray-100" />
            {Object.entries(stats.node_counts).map(([label, count]) => (
              <div key={label} className="flex justify-between text-gray-500">
                <span>{label}</span>
                <span>{count}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
