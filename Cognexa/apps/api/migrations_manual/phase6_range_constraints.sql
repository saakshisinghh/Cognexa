-- apps/api/migrations_manual/phase6_range_constraints.sql
--
-- Only needed if you already deployed asset_knowledge_gaps /
-- asset_knowledge_loss_risk BEFORE this update (i.e. create_all() already
-- created them without these constraints). If you have not deployed
-- Phase 6 Feature 2/3 yet, skip this file entirely — the updated
-- knowledge_gap.py / knowledge_loss.py model files already include these
-- constraints, so create_all() will add them automatically on first
-- creation.
--
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'ck_asset_knowledge_gap_score_range'
    ) THEN
        ALTER TABLE asset_knowledge_gaps
            ADD CONSTRAINT ck_asset_knowledge_gap_score_range
            CHECK (gap_score >= 0.0 AND gap_score <= 1.0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'ck_asset_loss_risk_score_range'
    ) THEN
        ALTER TABLE asset_knowledge_loss_risk
            ADD CONSTRAINT ck_asset_loss_risk_score_range
            CHECK (risk_score >= 0.0 AND risk_score <= 1.0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'ck_asset_loss_concentration_range'
    ) THEN
        ALTER TABLE asset_knowledge_loss_risk
            ADD CONSTRAINT ck_asset_loss_concentration_range
            CHECK (concentration_score >= 0.0 AND concentration_score <= 1.0);
    END IF;
END $$;
