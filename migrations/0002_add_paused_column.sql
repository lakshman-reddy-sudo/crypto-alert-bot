-- 0002_add_paused_column.sql
-- Adds the `paused` flag to support /alert pause and /alert resume
-- without deleting the alert.
--
-- The IF NOT EXISTS guards make this idempotent — safe to re-run
-- if the column was already created manually in Supabase.

ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS paused BOOLEAN NOT NULL DEFAULT FALSE;

-- Replace the old active-only index with one that also excludes paused alerts
-- so the WebSocket hot path only sees alerts that should actually fire.
DROP INDEX IF EXISTS idx_alerts_active_symbol;

CREATE INDEX IF NOT EXISTS idx_alerts_active_symbol
    ON alerts (symbol) WHERE active = TRUE AND paused = FALSE;
