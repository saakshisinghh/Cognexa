"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Plus, Trash2, Users2, Sparkles } from "lucide-react";
import toast from "react-hot-toast";

import AppLayout from "@/components/layout/AppLayout";
import { captureEntry, listEntries, deactivateEntry, listExperts } from "@/lib/api/persona";
import { useAuthStore } from "@/store/auth";

export default function ShadowEngineerPage() {
  const { user } = useAuthStore();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tagsInput, setTagsInput] = useState("");

  const myEntriesQuery = useQuery({
    queryKey: ["persona", "entries", user?.id],
    queryFn: () => listEntries(user?.id),
    enabled: !!user?.id,
  });

  const expertsQuery = useQuery({ queryKey: ["persona", "experts"], queryFn: () => listExperts() });

  const captureMutation = useMutation({
    mutationFn: () =>
      captureEntry(
        title,
        content,
        undefined,
        tagsInput.split(",").map((t) => t.trim()).filter(Boolean)
      ),
    onSuccess: () => {
      toast.success("Knowledge captured");
      setTitle("");
      setContent("");
      setTagsInput("");
      queryClient.invalidateQueries({ queryKey: ["persona"] });
    },
    onError: () => toast.error("Failed to capture knowledge — please try again"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deactivateEntry(id),
    onSuccess: () => {
      toast.success("Entry removed");
      queryClient.invalidateQueries({ queryKey: ["persona"] });
    },
  });

  return (
    <AppLayout>
      <div className="p-8 max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-primary" /> Shadow Engineer
        </h1>
        <p className="text-muted-foreground text-sm mt-1 mb-6">
          Capture the tips, workarounds, and tribal knowledge that never made it into a formal document —
          the Copilot can draw on it when you ask it to answer as a specific expert.
        </p>

        {/* Capture form */}
        <div className="bg-card border border-border rounded-xl p-5 mb-8">
          <h3 className="text-sm font-semibold text-foreground mb-3">Capture new knowledge</h3>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Short title, e.g. 'K-201 vibration quirk after cold starts'"
            className="w-full border border-border bg-background text-foreground rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Describe it in your own words — as much detail as you'd give a new engineer shadowing you."
            rows={5}
            className="w-full border border-border bg-background text-foreground rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-primary resize-none"
          />
          <input
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="Tags, comma-separated (optional)"
            className="w-full border border-border bg-background text-foreground rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <button
            onClick={() => captureMutation.mutate()}
            disabled={!title.trim() || !content.trim() || captureMutation.isPending}
            className="flex items-center gap-2 bg-primary text-primary-foreground text-sm font-medium px-4 py-2 rounded-lg hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed transition-colors"
          >
            <Plus className="w-4 h-4" />
            Capture
          </button>
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* My entries */}
          <div>
            <h3 className="text-sm font-semibold text-foreground mb-3">My entries</h3>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {(myEntriesQuery.data ?? []).map((entry) => (
                <div key={entry.id} className="p-4 border-b border-border last:border-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{entry.title}</p>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{entry.content}</p>
                      <p className="text-[10px] text-muted-foreground/70 mt-1">
                        {formatDistanceToNow(new Date(entry.created_at), { addSuffix: true })}
                      </p>
                    </div>
                    <button
                      onClick={() => deleteMutation.mutate(entry.id)}
                      className="text-muted-foreground hover:text-destructive shrink-0"
                      title="Remove"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
              {myEntriesQuery.isSuccess && myEntriesQuery.data.length === 0 && (
                <div className="p-6 text-center text-sm text-muted-foreground">
                  Nothing captured yet — add your first entry above.
                </div>
              )}
            </div>
          </div>

          {/* Expert directory */}
          <div>
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <Users2 className="w-4 h-4" /> Expert directory
            </h3>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {(expertsQuery.data ?? []).map((expert) => (
                <div key={expert.user_id} className="p-4 border-b border-border last:border-0 flex items-center justify-between">
                  <span className="text-sm text-foreground">{expert.full_name}</span>
                  <span className="text-xs text-muted-foreground bg-accent px-2 py-0.5 rounded-full">
                    {expert.entry_count} entr{expert.entry_count !== 1 ? "ies" : "y"}
                  </span>
                </div>
              ))}
              {expertsQuery.isSuccess && expertsQuery.data.length === 0 && (
                <div className="p-6 text-center text-sm text-muted-foreground">
                  No experts have captured knowledge yet.
                </div>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              To ask the Copilot to answer as a specific expert, select them from the persona
              picker in the Copilot chat.
            </p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
