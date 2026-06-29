"use client";

import { useState, useRef, useEffect, useCallback, Suspense } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import api from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";
import { formatRelativeTime, cn } from "@/lib/utils";
import type { Conversation, Message, MessageSource } from "@/types";
import {
  Send, Plus, MessageSquare, Trash2, Bot, User,
  FileText, ChevronDown, Loader2, Zap, ExternalLink
} from "lucide-react";

interface StreamChunk {
  type: "chunk" | "done" | "error";
  content?: string;
  sources?: MessageSource[];
  confidence?: number;
}

function SourceCard({ source }: { source: MessageSource }) {
  return (
    <div className="flex items-start gap-2 p-2 bg-muted/50 rounded border border-border text-xs">
      <FileText className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
      <div className="min-w-0">
        <p className="font-medium truncate">{source.source || "Document"}</p>
        <p className="text-muted-foreground">
          {source.page_number ? `Page ${source.page_number} · ` : ""}
          Score: {(source.score * 100).toFixed(0)}%
        </p>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message & { streaming?: boolean } }) {
  const isUser = message.role === "user";
  const [showSources, setShowSources] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <div className={cn(
        "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
        isUser ? "bg-primary/20" : "bg-indus-600"
      )}>
        {isUser ? <User className="w-4 h-4 text-primary" /> : <Zap className="w-4 h-4 text-white" />}
      </div>
      <div className={cn("flex flex-col max-w-[75%]", isUser ? "items-end" : "items-start")}>
        <div className={cn(
          "px-4 py-3 rounded-2xl text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-tr-sm"
            : "bg-card border border-border rounded-tl-sm"
        )}>
          {message.content}
          {(message as { streaming?: boolean }).streaming && (
            <span className="inline-block w-1.5 h-4 bg-current ml-1 animate-pulse rounded-sm" />
          )}
        </div>

        {!isUser && message.sources?.length > 0 && (
          <div className="mt-2 w-full">
            <button
              onClick={() => setShowSources((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition"
            >
              <FileText className="w-3 h-3" />
              {message.sources.length} source{message.sources.length > 1 ? "s" : ""}
              {message.confidence && (
                <span className="ml-2 text-primary font-medium">
                  {(message.confidence * 100).toFixed(0)}% confidence
                </span>
              )}
              <ChevronDown className={cn("w-3 h-3 transition", showSources && "rotate-180")} />
            </button>
            <AnimatePresence>
              {showSources && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="grid grid-cols-2 gap-1.5 mt-2">
                    {message.sources.map((s, i) => <SourceCard key={i} source={s} />)}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
        <span className="text-[10px] text-muted-foreground mt-1 px-1">
          {formatRelativeTime(message.created_at)}
        </span>
      </div>
    </motion.div>
  );
}

function CopilotPageInner() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const preselectedDoc = searchParams.get("document");
  const preselectedConvo = searchParams.get("conversation");

  const [activeConvoId, setActiveConvoId] = useState<string | null>(preselectedConvo);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingMsg, setStreamingMsg] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => { scrollToBottom(); }, [streamingMsg, scrollToBottom]);

  const { data: conversations } = useQuery<{ items: Conversation[]; total: number }>({
    queryKey: ["conversations"],
    queryFn: () => api.get("/copilot/conversations").then((r) => r.data),
    refetchInterval: 30_000,
  });

  const { data: activeConvo, refetch: refetchConvo } = useQuery<Conversation>({
    queryKey: ["conversation", activeConvoId],
    queryFn: () => api.get(`/copilot/conversations/${activeConvoId}`).then((r) => r.data),
    enabled: !!activeConvoId,
  });

  const createConvo = useMutation({
    mutationFn: (documentId?: string) =>
      api.post("/copilot/conversations", { document_id: documentId || null }).then((r) => r.data),
    onSuccess: (data: Conversation) => {
      setActiveConvoId(data.id);
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const deleteConvo = useMutation({
    mutationFn: (id: string) => api.delete(`/copilot/conversations/${id}`),
    onSuccess: () => {
      if (activeConvoId) setActiveConvoId(null);
      qc.invalidateQueries({ queryKey: ["conversations"] });
      toast.success("Conversation deleted");
    },
  });

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;

    let convoId = activeConvoId;
    if (!convoId) {
      const newConvo = await createConvo.mutateAsync(preselectedDoc || undefined);
      convoId = newConvo.id;
    }

    const userMessage = input.trim();
    setInput("");
    setIsStreaming(true);
    setStreamingMsg("");

    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const token = localStorage.getItem("access_token");

      const response = await fetch(`${API_BASE}/api/v1/copilot/conversations/${convoId}/messages/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ content: userMessage }),
      });

      if (!response.ok) throw new Error("Stream request failed");

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data: StreamChunk = JSON.parse(line.slice(6));
            if (data.type === "chunk" && data.content) {
              setStreamingMsg((prev) => prev + data.content);
            } else if (data.type === "done") {
              setStreamingMsg("");
              refetchConvo();
              qc.invalidateQueries({ queryKey: ["conversations"] });
            } else if (data.type === "error") {
              toast.error(data.content || "Generation failed");
            }
          } catch {
            // ignore parse errors on empty lines
          }
        }
      }
    } catch (err) {
      toast.error("Failed to send message");
      console.error(err);
    } finally {
      setIsStreaming(false);
      setStreamingMsg("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <AppLayout>
      <div className="flex h-full">
        {/* Sidebar - conversation list */}
        <aside className="w-64 border-r border-border flex flex-col bg-card/50">
          <div className="p-4 border-b border-border">
            <button
              onClick={() => { setActiveConvoId(null); createConvo.mutate(preselectedDoc || undefined); }}
              className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition"
            >
              <Plus className="w-4 h-4" />
              New Conversation
            </button>
          </div>

          <div className="flex-1 overflow-auto p-2 space-y-0.5">
            {conversations?.items.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-8">No conversations yet</p>
            )}
            {conversations?.items.map((c) => (
              <div
                key={c.id}
                className={cn(
                  "group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition",
                  activeConvoId === c.id ? "bg-primary/10 text-primary" : "hover:bg-accent text-foreground"
                )}
                onClick={() => setActiveConvoId(c.id)}
              >
                <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                <span className="flex-1 text-xs truncate">{c.title || "Untitled"}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); deleteConvo.mutate(c.id); }}
                  className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-destructive transition"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </aside>

        {/* Chat area */}
        <div className="flex-1 flex flex-col">
          {/* Header */}
          <div className="p-4 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 indus-gradient rounded-lg flex items-center justify-center">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <div>
                <p className="font-semibold text-sm">INDUS MIND Copilot</p>
                <p className="text-xs text-muted-foreground">
                  {activeConvo?.title || "Ask anything about your documents"}
                </p>
              </div>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-auto p-6 space-y-6">
            {!activeConvoId && (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="w-16 h-16 indus-gradient rounded-2xl flex items-center justify-center mb-4">
                  <Zap className="w-8 h-8 text-white" />
                </div>
                <h2 className="text-lg font-semibold mb-2">Industrial Knowledge Copilot</h2>
                <p className="text-muted-foreground text-sm max-w-sm">
                  Ask questions about your uploaded documents. The copilot retrieves relevant information and answers with sources.
                </p>
                <div className="mt-6 grid grid-cols-1 gap-2 w-full max-w-sm">
                  {[
                    "What are the maintenance procedures for pump P-101?",
                    "Summarize the safety requirements in this document",
                    "What is the MTBF specification for this equipment?",
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => setInput(q)}
                      className="px-4 py-3 bg-card border border-border rounded-lg text-sm text-left hover:border-primary/50 hover:bg-accent transition"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {activeConvo?.messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {/* Streaming placeholder */}
            {isStreaming && streamingMsg && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-indus-600 flex items-center justify-center shrink-0">
                  <Zap className="w-4 h-4 text-white" />
                </div>
                <div className="bg-card border border-border px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed max-w-[75%]">
                  {streamingMsg}
                  <span className="inline-block w-1.5 h-4 bg-current ml-1 animate-pulse rounded-sm" />
                </div>
              </div>
            )}

            {isStreaming && !streamingMsg && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-indus-600 flex items-center justify-center shrink-0">
                  <Zap className="w-4 h-4 text-white" />
                </div>
                <div className="bg-card border border-border px-4 py-3 rounded-2xl rounded-tl-sm flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Thinking…</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-4 border-t border-border">
            <div className="flex items-end gap-3 bg-card border border-border rounded-xl p-3 focus-within:border-primary transition">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your documents… (Enter to send, Shift+Enter for newline)"
                className="flex-1 bg-transparent resize-none text-sm focus:outline-none max-h-32 leading-relaxed"
                rows={1}
                style={{ height: "auto" }}
                onInput={(e) => {
                  const t = e.target as HTMLTextAreaElement;
                  t.style.height = "auto";
                  t.style.height = `${Math.min(t.scrollHeight, 128)}px`;
                }}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                className="w-9 h-9 rounded-lg indus-gradient flex items-center justify-center shrink-0 hover:opacity-90 transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isStreaming ? (
                  <Loader2 className="w-4 h-4 text-white animate-spin" />
                ) : (
                  <Send className="w-4 h-4 text-white" />
                )}
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground text-center mt-2">
              Answers grounded in your uploaded documents · Always verify critical information
            </p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}

export default function CopilotPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>}>
      <CopilotPageInner />
    </Suspense>
  );
}