"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";
import {
  Search, AlertOctagon, FileText, Wrench, ClipboardCheck, History as HistoryIcon, Clock,
} from "lucide-react";

import AppLayout from "@/components/layout/AppLayout";
import api from "@/lib/api";
import { getAssetTimeline, replayAssetState } from "@/lib/api/timeline";
import type { TimelineEventType } from "@/lib/types/knowledge";

interface AssetOption {
  id: string;
  // FIX: was `tag_number` + `asset_name` — the Asset model
  // (apps/api/models/__init__.py) has no `tag_number` field at all, and
  // the name field is called `name`, not `asset_name`. Every dropdown row
  // was rendering "undefined (undefined)" (or would have, once the
  // `items` vs `assets` bug above was fixed). Using the real fields:
  // `name` and `asset_type` (as a secondary descriptor in place of the
  // tag number that doesn't exist on this model).
  name: string;
  asset_type: string;
}

const EVENT_ICON: Record<TimelineEventType, typeof FileText> = {
  incident: AlertOctagon,
  document: FileText,
  work_order: Wrench,
  inspection: ClipboardCheck,
  knowledge_superseded: HistoryIcon,
};

const EVENT_COLOR: Record<TimelineEventType, string> = {
  incident: "text-red-400 bg-red-500/10",
  document: "text-blue-400 bg-blue-500/10",
  work_order: "text-violet-400 bg-violet-500/10",
  inspection: "text-teal-400 bg-teal-500/10",
  knowledge_superseded: "text-amber-400 bg-amber-500/10",
};

export default function TimeMachinePage() {
  const [search, setSearch] = useState("");
  const [selectedAsset, setSelectedAsset] = useState<AssetOption | null>(null);
  const [replayAt, setReplayAt] = useState<string>("");

  const assetSearchQuery = useQuery({
    queryKey: ["assets", "search", search],
    queryFn: async () => {
      const res = await api.get("/assets", { params: { page: 1, page_size: 8, search: search || undefined } });
      // FIX: was `res.data.assets` — the backend's AssetListResponse
      // (apps/api/schemas/__init__.py) returns the paginated list under
      // `items`, not `assets`. Reading the wrong key meant this always
      // evaluated to `undefined`, so the search dropdown could never show
      // results — the page looked permanently empty no matter what you
      // searched for.
      return res.data.items as AssetOption[];
    },
    enabled: search.length > 0,
  });

  const timelineQuery = useQuery({
    queryKey: ["timeline", selectedAsset?.id],
    queryFn: () => getAssetTimeline(selectedAsset!.id),
    enabled: !!selectedAsset,
  });

  const replayQuery = useQuery({
    queryKey: ["timeline", "replay", selectedAsset?.id, replayAt],
    queryFn: () => replayAssetState(selectedAsset!.id, new Date(replayAt).toISOString()),
    enabled: !!selectedAsset && !!replayAt,
  });

  return (
    <AppLayout>
      <div className="p-8 max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-foreground">Failure Time Machine</h1>
        <p className="text-muted-foreground text-sm mt-1 mb-6">
          Replay an asset's incident, document, and knowledge history — or jump back to see what was known at any point in time
        </p>

        {/* Asset picker */}
        <div className="relative mb-6">
          <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 bg-card">
            <Search className="w-4 h-4 text-muted-foreground" />
            <input
              value={selectedAsset ? `${selectedAsset.name} (${selectedAsset.asset_type})` : search}
              onChange={(e) => {
                setSelectedAsset(null);
                setSearch(e.target.value);
              }}
              placeholder="Search for an asset…"
              className="flex-1 bg-transparent text-sm text-foreground placeholder-muted-foreground focus:outline-none"
            />
          </div>
          {search && !selectedAsset && (assetSearchQuery.data?.length ?? 0) > 0 && (
            <ul className="absolute z-10 mt-1 w-full bg-popover border border-border rounded-lg shadow-xl max-h-60 overflow-y-auto">
              {assetSearchQuery.data!.map((asset) => (
                <li key={asset.id}>
                  <button
                    onClick={() => {
                      setSelectedAsset(asset);
                      setSearch("");
                    }}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-primary/10"
                  >
                    <span className="font-mono text-primary font-semibold">{asset.asset_type}</span>{" "}
                    <span className="text-muted-foreground">{asset.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {!selectedAsset && (
          <div className="text-center text-sm text-muted-foreground py-16 border border-dashed border-border rounded-xl">
            Search for an asset above to see its timeline
          </div>
        )}

        {selectedAsset && (
          <div className="grid grid-cols-3 gap-6">
            {/* Timeline */}
            <div className="col-span-2 bg-card border border-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-foreground mb-4">Timeline</h3>
              <div className="space-y-0">
                {(timelineQuery.data?.events ?? []).map((event, i) => {
                  const Icon = EVENT_ICON[event.event_type];
                  return (
                    <div key={i} className="flex gap-3 pb-6 relative">
                      {i < (timelineQuery.data?.events.length ?? 0) - 1 && (
                        <div className="absolute left-4 top-8 bottom-0 w-px bg-border" />
                      )}
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${EVENT_COLOR[event.event_type]}`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="flex-1 min-w-0 pt-1">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-foreground">{event.title}</span>
                          <span className="text-[10px] text-muted-foreground shrink-0 ml-2">
                            {format(new Date(event.occurred_at), "MMM d, yyyy")}
                          </span>
                        </div>
                        {event.description && (
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{event.description}</p>
                        )}
                        {event.severity && (
                          <span className="inline-block mt-1 text-[10px] uppercase tracking-wide text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded">
                            {event.severity}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
                {timelineQuery.isSuccess && timelineQuery.data.events.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">No timeline events for this asset yet.</p>
                )}
              </div>
            </div>

            {/* Replay panel */}
            <div className="bg-card border border-border rounded-xl p-5 h-fit">
              <h3 className="text-sm font-semibold text-foreground mb-1 flex items-center gap-2">
                <Clock className="w-4 h-4" /> Replay
              </h3>
              <p className="text-xs text-muted-foreground mb-3">See what was known as of a past date</p>
              <input
                type="date"
                value={replayAt}
                onChange={(e) => setReplayAt(e.target.value)}
                className="w-full border border-border bg-background text-foreground rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary mb-4"
              />

              {replayQuery.data && (
                <div className="space-y-4 text-xs">
                  <div>
                    <p className="text-muted-foreground mb-1">
                      {replayQuery.data.documents_existing_to_date} document(s) existed
                    </p>
                    <p className="text-muted-foreground">
                      {replayQuery.data.valid_chunks.length} chunk(s) were valid
                    </p>
                    <p className="text-muted-foreground">
                      {replayQuery.data.incidents_to_date.length} incident(s) had occurred
                    </p>
                  </div>
                  {replayQuery.data.incidents_to_date.slice(0, 5).map((inc) => (
                    <div key={inc.incident_id} className="border-t border-border pt-2">
                      <p className="text-foreground font-medium">{inc.title}</p>
                      <p className="text-muted-foreground">{format(new Date(inc.occurred_at), "MMM d, yyyy")}</p>
                    </div>
                  ))}
                  <p className="text-[10px] text-muted-foreground/70 italic pt-2 border-t border-border">
                    {replayQuery.data.note}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}