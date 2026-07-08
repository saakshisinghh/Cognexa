-- apps/api/migrations_manual/phase6_disagreement.sql
--
-- Phase 6 — Expert Disagreement Detection: optional performance index.
--
-- AssetExpertDisagreement itself is a brand-new table (auto-created by
-- create_all()) — no manual SQL needed for it. This index is purely an
-- optimization for the nightly task's
--   SELECT conflicts_json, created_at FROM query_history WHERE conflict_detected = TRUE
-- scan, since most rows will have conflict_detected = FALSE. Skip this
-- if query_history is still small — it only matters once that table has
-- grown to tens of thousands of rows.

CREATE INDEX IF NOT EXISTS ix_query_history_conflict_detected
    ON query_history (conflict_detected)
    WHERE conflict_detected = TRUE;
