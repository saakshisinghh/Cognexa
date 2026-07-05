"use client";

/**
 * apps/web/components/copilot/AssetContextBadge.tsx
 *
 * Shows the currently pinned asset in the copilot header.
 * Clicking it opens a small popover to change or clear the pin.
 * Asset search uses the existing GET /api/v1/assets?q= endpoint
 * from Phase 1 — no new backend call added.
 */

import { useState, useRef, useEffect } from "react";
import { pinAsset } from "@/lib/api/copilot";

interface AssetResult {
  id: string;
  tag_number: string;
  asset_name: string;
  asset_type: string;
}

interface Props {
  sessionId: string | null;
  pinnedAssetTag: string | null;
  onPinChanged: (tag: string | null) => void;
}

async function searchAssets(q: string): Promise<AssetResult[]> {
  if (!q.trim()) return [];
  const res = await fetch(`/api/v1/assets?q=${encodeURIComponent(q)}&limit=8`);
  if (!res.ok) return [];
  const data = await res.json();
  // Phase 1 returns { assets: [...] } or a list — handle both shapes.
  return Array.isArray(data) ? data : (data.assets ?? []);
}

export function AssetContextBadge({ sessionId, pinnedAssetTag, onPinChanged }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AssetResult[]>([]);
  const [loading, setLoading] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Close popover on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Focus input when popover opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
      setResults([]);
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (!query) { setResults([]); return; }
    const timer = setTimeout(() => {
      setLoading(true);
      searchAssets(query)
        .then(setResults)
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  async function handlePin(asset: AssetResult | null) {
    if (!sessionId) return;
    try {
      await pinAsset(
        sessionId,
        asset?.id ?? null,
        asset?.tag_number ?? null,
      );
      onPinChanged(asset?.tag_number ?? null);
      setOpen(false);
    } catch {
      // non-fatal; user sees no change
    }
  }

  return (
    <div className="relative" ref={popoverRef}>
      {/* Trigger button */}
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={!sessionId}
        className={`
          flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
          transition-colors border
          ${pinnedAssetTag
            ? "bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100"
            : "bg-gray-100 border-gray-200 text-gray-500 hover:bg-gray-200"
          }
          disabled:opacity-40 disabled:cursor-not-allowed
        `}
        title={pinnedAssetTag ? `Pinned: ${pinnedAssetTag}. Click to change.` : "Pin an asset to focus queries"}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span aria-hidden>{pinnedAssetTag ? "📌" : "🔍"}</span>
        <span className="max-w-[120px] truncate">
          {pinnedAssetTag ?? "Asset context"}
        </span>
        {pinnedAssetTag && (
          <span
            className="text-blue-400 hover:text-blue-700"
            onClick={(e) => { e.stopPropagation(); handlePin(null); }}
            title="Remove pin"
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && handlePin(null)}
          >
            ×
          </span>
        )}
      </button>

      {/* Popover */}
      {open && (
        <div
          className="
            absolute top-full left-0 mt-1 w-72 z-50
            bg-white border border-gray-200 rounded-xl shadow-xl
            overflow-hidden
          "
          role="dialog"
          aria-label="Select asset context"
        >
          <div className="p-2 border-b border-gray-100">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search asset tag (P-1045, K-201…)"
              className="
                w-full px-3 py-2 text-sm rounded-lg border border-gray-200
                focus:outline-none focus:ring-2 focus:ring-indigo-400
              "
              role="searchbox"
            />
          </div>

          <ul
            className="max-h-56 overflow-y-auto py-1"
            role="listbox"
            aria-label="Asset search results"
          >
            {/* Clear pin option */}
            {pinnedAssetTag && (
              <li>
                <button
                  onClick={() => handlePin(null)}
                  className="w-full text-left px-3 py-2 text-sm text-red-500 hover:bg-red-50"
                >
                  ✕ Remove asset context
                </button>
              </li>
            )}

            {loading && (
              <li className="px-3 py-2 text-sm text-gray-400">Searching…</li>
            )}

            {!loading && query && results.length === 0 && (
              <li className="px-3 py-2 text-sm text-gray-400">No assets found.</li>
            )}

            {results.map((asset) => (
              <li key={asset.id} role="option" aria-selected={asset.tag_number === pinnedAssetTag}>
                <button
                  onClick={() => handlePin(asset)}
                  className={`
                    w-full text-left px-3 py-2 text-sm hover:bg-indigo-50
                    ${asset.tag_number === pinnedAssetTag ? "bg-indigo-50 font-semibold" : ""}
                  `}
                >
                  <span className="font-mono text-indigo-700 font-semibold">{asset.tag_number}</span>
                  {" "}
                  <span className="text-gray-500">
                    {asset.asset_name}
                    {asset.asset_type && ` · ${asset.asset_type}`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
