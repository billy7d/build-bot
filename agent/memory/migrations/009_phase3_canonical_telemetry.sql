-- Phase 3.1 lưu raw opportunity và canonical evidence riêng với stream execution cũ.

CREATE TABLE IF NOT EXISTS phase3_opportunity_observations (
    observation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES phase3_forward_runs(run_id),
    source_observation_id TEXT NOT NULL,
    event_timestamp_utc TEXT NOT NULL,
    emitted_at_utc TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    source_strategy TEXT NOT NULL,
    source_strategy_version TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    side TEXT NOT NULL,
    source_audit_family TEXT NOT NULL,
    source_event_type TEXT NOT NULL,
    bar_state TEXT NOT NULL CHECK (bar_state = 'closed_bar'),
    context_features_json TEXT NOT NULL,
    execution_context_json TEXT NOT NULL,
    entry_price REAL,
    hypothetical_entry_price REAL,
    risk_distance REAL,
    initial_sl_distance REAL,
    hypothetical_initial_sl REAL,
    build_valid INTEGER NOT NULL CHECK (build_valid IN (0, 1)),
    build_reason TEXT,
    canonical_opportunity_id TEXT NOT NULL,
    canonical_schema TEXT NOT NULL,
    canonicalizer_version TEXT NOT NULL,
    canonicalizer_fingerprint TEXT NOT NULL,
    raw_payload_sha256 TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE (run_id, source_observation_id)
);

CREATE TABLE IF NOT EXISTS phase3_canonical_opportunities (
    canonical_record_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES phase3_forward_runs(run_id),
    canonical_opportunity_id TEXT NOT NULL,
    representative_observation_id TEXT NOT NULL REFERENCES phase3_opportunity_observations(observation_id),
    event_timestamp_utc TEXT NOT NULL,
    source_strategy_version TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    side TEXT NOT NULL,
    canonical_schema TEXT NOT NULL,
    canonicalizer_version TEXT NOT NULL,
    canonicalizer_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    raw_observation_count INTEGER NOT NULL CHECK (raw_observation_count >= 1),
    duplicate_observation_count INTEGER NOT NULL CHECK (duplicate_observation_count >= 0),
    build_valid INTEGER NOT NULL CHECK (build_valid IN (0, 1)),
    build_reason TEXT,
    score_status TEXT NOT NULL,
    forward_event_id TEXT,
    prediction_id TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE (run_id, canonical_opportunity_id)
);

ALTER TABLE phase3_forward_events
    ADD COLUMN source_role TEXT NOT NULL DEFAULT 'EXECUTION_DIAGNOSTIC';
ALTER TABLE phase3_forward_events
    ADD COLUMN canonical_opportunity_id TEXT;

ALTER TABLE phase3_predictions
    ADD COLUMN source_role TEXT NOT NULL DEFAULT 'EXECUTION_DIAGNOSTIC';
ALTER TABLE phase3_predictions
    ADD COLUMN canonical_opportunity_id TEXT;

CREATE INDEX IF NOT EXISTS idx_phase3_observations_run_time
    ON phase3_opportunity_observations(run_id, event_timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_phase3_observations_canonical
    ON phase3_opportunity_observations(run_id, canonical_opportunity_id);
CREATE INDEX IF NOT EXISTS idx_phase3_canonical_run_status
    ON phase3_canonical_opportunities(run_id, status, event_timestamp_utc);
CREATE UNIQUE INDEX IF NOT EXISTS idx_phase3_events_canonical_once
    ON phase3_forward_events(run_id, canonical_opportunity_id)
    WHERE canonical_opportunity_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_phase3_predictions_canonical_once
    ON phase3_predictions(forward_run_id, canonical_opportunity_id)
    WHERE canonical_opportunity_id IS NOT NULL;
