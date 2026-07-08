-- apps/api/migrations_manual/phase6_temporal.sql
--
-- Phase 6 — Temporal Knowledge Intelligence: one-time schema patch.
--
-- WHY THIS FILE EXISTS: Base.metadata.create_all() (called at API boot in
-- main.py) only CREATEs tables that don't exist yet — it does NOT add new
-- columns to tables that already exist. `chunks` and `documents` already
-- exist in your running Postgres with real data, so the new Phase 6
-- columns on the SQLAlchemy models will silently be ignored by create_all()
-- until you run this once, manually, against your database.
--
-- Safe to run multiple times (IF NOT EXISTS guards on every column).
-- Does not touch any existing column, row, or data.
--
-- Run it with:
--   docker compose exec -T db psql -U <user> -d <database> -f phase6_temporal.sql
-- (adjust to your actual postgres service name / credentials from .env)

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS superseded_by_chunk_id VARCHAR,
    ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS decay_computed_at TIMESTAMPTZ;

-- Backfill valid_from for any pre-existing rows using their created_at,
-- so the decay formula has a real starting point instead of "just now"
-- for documents ingested before this Phase 6 rollout.
UPDATE chunks SET valid_from = created_at WHERE valid_from IS NULL;

-- Self-referential FK — added separately since IF NOT EXISTS isn't
-- supported for ADD CONSTRAINT in older Postgres versions; the DO block
-- makes it idempotent instead.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'chunks_superseded_by_chunk_id_fkey'
    ) THEN
        ALTER TABLE chunks
            ADD CONSTRAINT chunks_superseded_by_chunk_id_fkey
            FOREIGN KEY (superseded_by_chunk_id) REFERENCES chunks(id) ON DELETE SET NULL;
    END IF;
END $$;

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS stale_flagged_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS stale_reason TEXT;

-- Helpful index for the nightly supersession sweep's asset+category grouping.
CREATE INDEX IF NOT EXISTS ix_documents_asset_id_category ON documents(asset_id, category);
