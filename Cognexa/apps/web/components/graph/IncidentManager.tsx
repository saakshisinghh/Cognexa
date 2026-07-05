/**
 * apps/web/components/graph/IncidentManager.tsx
 *
 * Purpose
 * -------
 * Incident CRUD UI for a given asset: list with severity/status badges,
 * create/edit form, delete with confirm. Mounted on the existing
 * Asset 360 "Incidents" tab (apps/web/app/assets/[id]/ — tab routing
 * already exists from Phase 1; this component is the new tab content).
 *
 * Dependencies
 * ------------
 * - apps/web/lib/graph/api.ts (createIncident, listIncidents, updateIncident, deleteIncident)
 *
 * This file is NEW.
 */

"use client";

import React, { useEffect, useState } from "react";
import {
  IncidentResponse,
  IncidentPayload,
  listIncidents,
  createIncident,
  updateIncident,
  deleteIncident,
} from "@/lib/graph/api";

const SEVERITY_COLORS: Record<string, string> = {
  low: "bg-gray-100 text-gray-700",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

const STATUS_COLORS: Record<string, string> = {
  open: "bg-blue-100 text-blue-700",
  investigating: "bg-purple-100 text-purple-700",
  resolved: "bg-green-100 text-green-700",
  closed: "bg-gray-100 text-gray-500",
};

const SYNC_LABEL: Record<string, string> = {
  pending: "⏳ Syncing to graph…",
  synced: "✅ Synced to graph",
  failed: "❌ Graph sync failed",
};

interface IncidentManagerProps {
  assetId: string;
}

const emptyForm: IncidentPayload = {
  title: "",
  description: "",
  asset_id: "",
  severity: "medium",
  status: "open",
  failure_mode_code: "",
  occurred_at: new Date().toISOString().slice(0, 16),
};

export function IncidentManager({ assetId }: IncidentManagerProps) {
  const [incidents, setIncidents] = useState<IncidentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<IncidentPayload>({ ...emptyForm, asset_id: assetId });
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    listIncidents(assetId)
      .then(setIncidents)
      .catch((err: any) => setError(err?.message ?? "Failed to load incidents"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId]);

  const openCreateForm = () => {
    setForm({ ...emptyForm, asset_id: assetId });
    setEditingId(null);
    setShowForm(true);
  };

  const openEditForm = (incident: IncidentResponse) => {
    setForm({
      title: incident.title,
      description: incident.description,
      asset_id: incident.asset_id,
      severity: incident.severity,
      status: incident.status,
      failure_mode_code: incident.failure_mode_code ?? "",
      occurred_at: incident.occurred_at.slice(0, 16),
    });
    setEditingId(incident.id);
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingId) {
        await updateIncident(editingId, form);
      } else {
        await createIncident({ ...form, occurred_at: new Date(form.occurred_at).toISOString() });
      }
      setShowForm(false);
      load();
    } catch (err: any) {
      setError(err?.message ?? "Failed to save incident");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this incident? This also removes it from the knowledge graph.")) return;
    try {
      await deleteIncident(id);
      load();
    } catch (err: any) {
      setError(err?.message ?? "Failed to delete incident");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800">Incidents</h3>
        <button
          onClick={openCreateForm}
          className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
        >
          + New Incident
        </button>
      </div>

      {error && <p className="rounded bg-red-50 p-2 text-xs text-red-600">{error}</p>}

      {loading && <p className="text-xs text-gray-400">Loading incidents…</p>}

      {!loading && incidents.length === 0 && (
        <p className="text-xs text-gray-400">No incidents recorded for this asset yet.</p>
      )}

      <div className="flex flex-col gap-2">
        {incidents.map((incident) => (
          <div key={incident.id} className="rounded border border-gray-200 p-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm font-medium text-gray-800">{incident.title}</p>
                <p className="mt-0.5 text-xs text-gray-500">{incident.description}</p>
              </div>
              <div className="flex shrink-0 gap-2">
                <button onClick={() => openEditForm(incident)} className="text-xs text-blue-600 hover:underline">
                  Edit
                </button>
                <button onClick={() => handleDelete(incident.id)} className="text-xs text-red-600 hover:underline">
                  Delete
                </button>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span className={`rounded px-2 py-0.5 ${SEVERITY_COLORS[incident.severity]}`}>
                {incident.severity}
              </span>
              <span className={`rounded px-2 py-0.5 ${STATUS_COLORS[incident.status]}`}>
                {incident.status}
              </span>
              <span className="text-gray-400">{SYNC_LABEL[incident.graph_sync_status]}</span>
              <span className="ml-auto text-gray-400">
                {new Date(incident.occurred_at).toLocaleString()}
              </span>
            </div>
          </div>
        ))}
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <form
            onSubmit={handleSubmit}
            className="w-full max-w-md rounded-lg bg-white p-5 shadow-lg"
          >
            <h4 className="mb-3 text-sm font-semibold">
              {editingId ? "Edit Incident" : "New Incident"}
            </h4>

            <label className="mb-1 block text-xs font-medium text-gray-600">Title</label>
            <input
              required
              minLength={3}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />

            <label className="mb-1 block text-xs font-medium text-gray-600">Description</label>
            <textarea
              required
              minLength={10}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
              rows={3}
            />

            <div className="mb-3 grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Severity</label>
                <select
                  value={form.severity}
                  onChange={(e) => setForm({ ...form, severity: e.target.value as IncidentPayload["severity"] })}
                  className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                >
                  {["low", "medium", "high", "critical"].map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Status</label>
                <select
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value as IncidentPayload["status"] })}
                  className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                >
                  {["open", "investigating", "resolved", "closed"].map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>

            <label className="mb-1 block text-xs font-medium text-gray-600">
              Failure Mode Code (optional)
            </label>
            <input
              value={form.failure_mode_code ?? ""}
              onChange={(e) => setForm({ ...form, failure_mode_code: e.target.value })}
              placeholder="FM-003"
              className="mb-3 w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />

            <label className="mb-1 block text-xs font-medium text-gray-600">Occurred At</label>
            <input
              required
              type="datetime-local"
              value={form.occurred_at}
              onChange={(e) => setForm({ ...form, occurred_at: e.target.value })}
              className="mb-4 w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
            />

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
