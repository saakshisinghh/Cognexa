"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import { cn } from "@/lib/utils";
import type { SearchResponse, SearchResult } from "@/types";
import {
  Search, Loader2, FileText, Factory, Star,
  SlidersHorizontal, X, MessageSquare, ChevronRight
} from "lucide-react";

function ResultCard({ result, index }: { result: SearchResult; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className="bg-card border border-border rounded-xl p-5 hover:border-primary/40 transition group"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 bg-primary/10 rounded-lg flex items-center justify-center shrink-0">
            <FileText className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="min-w-0">
            <Link
              href={`/documents/${result.document_id}`}
              className="text-sm font-semibold hover:text-primary transition truncate block"
            >
              {result.document_name}
            </Link>
            {result.asset_name && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
                <Factory className="w-3 h-3" />
                {result.asset_name}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-4">
          {result.page_number && (
            <span className="text-xs text-muted-foreground">p.{result.page_number}</span>
          )}
          <div className="flex items-center gap-1 px-2 py-1 bg-primary/10 rounded text-xs text-primary font-medium">
            <Star className="w-3 h-3 fill-primary" />
            {(result.score * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      <p className="text-sm text-foreground/80 leading-relaxed line-clamp-3 mb-3">
        {result.highlight || result.text}
      </p>

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground font-mono">
          chunk #{result.chunk_index}
        </span>
        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition">
          <Link
            href={`/documents/${result.document_id}`}
            className="flex items-center gap-1 text-xs text-primary hover:underline"
          >
            View doc <ChevronRight className="w-3 h-3" />
          </Link>
          <Link
            href={`/copilot?document=${result.document_id}`}
            className="flex items-center gap-1 text-xs text-emerald-500 hover:underline"
          >
            <MessageSquare className="w-3 h-3" /> Ask
          </Link>
        </div>
      </div>
    </motion.div>
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [minScore, setMinScore] = useState(0);
  const [showFilters, setShowFilters] = useState(false);

  const searchMutation = useMutation({
    mutationFn: (q: string) =>
      api.post<SearchResponse>("/search", { query: q, top_k: topK, min_score: minScore })
        .then((r) => r.data),
  });

  const handleSearch = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    searchMutation.mutate(query.trim());
  };

  return (
    <AppLayout>
      <div className="p-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold">Semantic Search</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Search across all your documents using natural language
          </p>
        </div>

        {/* Search bar */}
        <form onSubmit={handleSearch} className="mb-4">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by meaning — e.g. 'pump bearing failure maintenance procedure'"
                className="w-full pl-12 pr-4 py-3.5 rounded-xl bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary placeholder:text-muted-foreground"
                autoFocus
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={() => setShowFilters((v) => !v)}
              className={cn(
                "px-4 rounded-xl border transition flex items-center gap-2 text-sm",
                showFilters ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-accent"
              )}
            >
              <SlidersHorizontal className="w-4 h-4" />
              Filters
            </button>
            <button
              type="submit"
              disabled={!query.trim() || searchMutation.isPending}
              className="px-6 py-3.5 rounded-xl indus-gradient text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 transition flex items-center gap-2"
            >
              {searchMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
              Search
            </button>
          </div>
        </form>

        {/* Filters panel */}
        <AnimatePresence>
          {showFilters && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden mb-4"
            >
              <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-6">
                <div className="flex items-center gap-3">
                  <label className="text-sm text-muted-foreground whitespace-nowrap">Results</label>
                  <select
                    value={topK}
                    onChange={(e) => setTopK(Number(e.target.value))}
                    className="px-3 py-2 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    {[5, 10, 20, 50].map((k) => (
                      <option key={k} value={k}>{k}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-3">
                  <label className="text-sm text-muted-foreground whitespace-nowrap">Min Score</label>
                  <select
                    value={minScore}
                    onChange={(e) => setMinScore(Number(e.target.value))}
                    className="px-3 py-2 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    {[0, 0.3, 0.5, 0.7, 0.8].map((s) => (
                      <option key={s} value={s}>{(s * 100).toFixed(0)}%</option>
                    ))}
                  </select>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Suggestions */}
        {!searchMutation.data && !searchMutation.isPending && (
          <div className="mb-6">
            <p className="text-xs text-muted-foreground mb-3 font-medium uppercase tracking-wider">Try searching for</p>
            <div className="flex flex-wrap gap-2">
              {[
                "maintenance procedure",
                "failure mode analysis",
                "safety requirements",
                "operating pressure specification",
                "inspection checklist",
                "torque specifications",
              ].map((s) => (
                <button
                  key={s}
                  onClick={() => { setQuery(s); }}
                  className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs hover:border-primary/50 hover:bg-accent transition"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Results */}
        {searchMutation.isPending && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
            <p className="text-muted-foreground text-sm">Searching across your documents…</p>
          </div>
        )}

        {searchMutation.data && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-sm font-medium">
                  {searchMutation.data.total} result{searchMutation.data.total !== 1 ? "s" : ""} for{" "}
                  <span className="text-primary">"{searchMutation.data.query}"</span>
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {searchMutation.data.took_ms.toFixed(0)}ms
                </p>
              </div>
            </div>

            {searchMutation.data.results.length === 0 ? (
              <div className="text-center py-16">
                <Search className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
                <p className="font-medium text-muted-foreground">No results found</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Try different keywords or upload more documents
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {searchMutation.data.results.map((result, i) => (
                  <ResultCard key={result.chunk_id} result={result} index={i} />
                ))}
              </div>
            )}
          </div>
        )}

        {searchMutation.isError && (
          <div className="text-center py-16">
            <p className="text-destructive font-medium">Search failed</p>
            <p className="text-sm text-muted-foreground mt-1">
              Please ensure documents are uploaded and processed
            </p>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
