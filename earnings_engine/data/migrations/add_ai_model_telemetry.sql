-- Migration: add ai_model_telemetry table for AI model telemetry tracking
-- This table is also auto-created by RateLimitTracker.hydrate_from_db() at startup.
-- This file serves as an explicit audit trail for the schema.

CREATE TABLE IF NOT EXISTS ai_model_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    model_name TEXT,
    created_at TEXT NOT NULL,
    timestamp REAL NOT NULL,
    latency_ms REAL NOT NULL,
    tokens INTEGER,
    is_local INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error_message TEXT,
    ticker TEXT
);

CREATE INDEX IF NOT EXISTS idx_telemetry_model ON ai_model_telemetry(model_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON ai_model_telemetry(timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_ticker ON ai_model_telemetry(ticker);
