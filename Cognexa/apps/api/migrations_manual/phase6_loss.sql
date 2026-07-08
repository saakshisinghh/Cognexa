-- apps/api/migrations_manual/phase6_loss.sql
--
-- Phase 6 — Knowledge Loss Prediction: one-time schema patch.
--
-- Same reasoning as phase6_temporal.sql: `users` already exists with real
-- data, so create_all() will NOT add these two new columns on its own —
-- run this once, manually.
--
-- (asset_expertise_ownership and asset_knowledge_loss_risk are brand-new
-- tables — those WILL be auto-created by create_all() at next API boot,
-- no manual SQL needed for them.)
--
-- Safe to run multiple times.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_retirement_risk BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS retirement_risk_notes TEXT;
