-- 0001_initial_schema.sql
-- Creates the alerts table and supporting indexes.
-- This is the canonical schema source. data.py's _CREATE_SCHEMA_SQL mirrors
-- this for the fast-path startup (avoids running the migrator in production
-- every restart), but this file is the authoritative version for migrations.

CREATE TABLE IF NOT EXISTS alerts (
    id                BIGSERIAL       PRIMARY KEY,
    user_id           BIGINT          NOT NULL,
    guild_id          BIGINT          NOT NULL,
    channel_id        BIGINT          NOT NULL,
    symbol            VARCHAR(20)     NOT NULL,
    direction         VARCHAR(10)     NOT NULL
                          CHECK (direction IN ('above', 'below', 'both')),
    target_price      NUMERIC(28, 8)  NOT NULL,
    last_price        NUMERIC(28, 8),
    repeat            BOOLEAN         NOT NULL DEFAULT FALSE,
    active            BOOLEAN         NOT NULL DEFAULT TRUE,
    last_triggered_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_active_symbol
    ON alerts (symbol) WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_alerts_user_active
    ON alerts (user_id) WHERE active = TRUE;
