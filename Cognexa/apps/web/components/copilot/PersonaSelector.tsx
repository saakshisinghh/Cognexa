"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { UserCog, X, ChevronDown } from "lucide-react";

import { listExperts } from "@/lib/api/persona";

interface PersonaSelectorProps {
  selectedPersonaId: string | null;
  onSelect: (userId: string | null) => void;
}

export function PersonaSelector({ selectedPersonaId, onSelect }: PersonaSelectorProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const expertsQuery = useQuery({ queryKey: ["persona", "experts"], queryFn: () => listExperts() });
  const selected = expertsQuery.data?.find((e) => e.user_id === selectedPersonaId);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!expertsQuery.data || expertsQuery.data.length === 0) return null;

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-full border transition-colors ${
          selected
            ? "bg-primary/10 border-primary/20 text-primary"
            : "bg-accent border-border text-muted-foreground hover:bg-accent/70"
        }`}
      >
        <UserCog className="w-3.5 h-3.5" />
        {selected ? `Answering as ${selected.full_name}` : "Answer as an expert"}
        <ChevronDown className="w-3 h-3" />
      </button>

      {selected && (
        <button
          onClick={() => onSelect(null)}
          className="absolute -right-1 -top-1 w-4 h-4 rounded-full bg-destructive/80 text-white flex items-center justify-center hover:bg-destructive"
          title="Clear persona"
        >
          <X className="w-2.5 h-2.5" />
        </button>
      )}

      {open && (
        <div className="absolute top-full left-0 mt-1 w-56 bg-popover border border-border rounded-xl shadow-xl z-10 max-h-64 overflow-y-auto">
          <button
            onClick={() => {
              onSelect(null);
              setOpen(false);
            }}
            className="w-full text-left px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
          >
            No persona (default)
          </button>
          {expertsQuery.data.map((expert) => (
            <button
              key={expert.user_id}
              onClick={() => {
                onSelect(expert.user_id);
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-primary/10 ${
                expert.user_id === selectedPersonaId ? "bg-primary/10 font-semibold text-primary" : "text-foreground"
              }`}
            >
              {expert.full_name}
              <span className="text-xs text-muted-foreground ml-1">({expert.entry_count})</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
