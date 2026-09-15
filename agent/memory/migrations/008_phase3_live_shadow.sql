-- Phase 3 bổ sung storage forward evidence, không sửa các migration lịch sử.

CREATE TABLE IF NOT EXISTS phase3_shadow_bundles (
    bundle_id TEXT PRIMARY KEY,
    bundle_version TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    phase1_fingerprint TEXT NOT NULL,
    phase2_base_sha TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    feature_fingerprint TEXT NOT NULL,
    preprocessing_fingerprint TEXT NOT NULL,
    regime_version TEXT NOT NULL,
    regime_fingerprint TEXT NOT NULL,
    similarity_version TEXT NOT NULL,
    similarity_fingerprint TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    calibration_fingerprint TEXT NOT NULL,
    historical_reference_cutoff_utc TEXT NOT NULL,
    seed INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('FROZEN', 'REVOKED'))
);

CREATE TABLE IF NOT EXISTS phase3_forward_runs (
    run_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL REFERENCES phase3_shadow_bundles(bundle_id),
    mode TEXT NOT NULL CHECK (mode IN ('SMOKE', 'REPLAY', 'FORWARD')),
    started_at_utc TEXT NOT NULL,
    stopped_at_utc TEXT,
    source TEXT NOT NULL,
    symbol TEXT,
    timeframe TEXT,
    git_sha TEXT NOT NULL,
    forward_start_utc TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CREATED', 'RUNNING', 'PAUSED', 'STOPPED', 'FAILED')),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3_ingest_offsets (
    source_key TEXT PRIMARY KEY,
    source_identity TEXT NOT NULL,
    source_path TEXT NOT NULL,
    offset_bytes INTEGER NOT NULL CHECK (offset_bytes >= 0),
    last_consumed_event_id TEXT,
    rotation_state_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3_forward_events (
    forward_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES phase3_forward_runs(run_id),
    forward_opportunity_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    event_timestamp_utc TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    side TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    bar_state TEXT NOT NULL,
    source_timezone TEXT,
    raw_payload_sha256 TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    failure_reason TEXT,
    created_at_utc TEXT NOT NULL,
    UNIQUE (run_id, source_event_id)
);

CREATE TABLE IF NOT EXISTS phase3_feature_snapshots (
    forward_event_id TEXT PRIMARY KEY REFERENCES phase3_forward_events(forward_event_id),
    feature_set_version TEXT NOT NULL,
    feature_timestamp_utc TEXT NOT NULL,
    feature_fingerprint TEXT NOT NULL,
    feature_values_json TEXT NOT NULL,
    missingness_json TEXT NOT NULL,
    ood_inputs_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3_predictions (
    prediction_id TEXT PRIMARY KEY,
    forward_event_id TEXT NOT NULL UNIQUE REFERENCES phase3_forward_events(forward_event_id),
    forward_run_id TEXT NOT NULL REFERENCES phase3_forward_runs(run_id),
    forward_opportunity_id TEXT NOT NULL,
    source_event_timestamp_utc TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    scored_at_utc TEXT NOT NULL,
    prediction_committed_at_utc TEXT NOT NULL,
    bundle_id TEXT NOT NULL REFERENCES phase3_shadow_bundles(bundle_id),
    feature_snapshot_fingerprint TEXT NOT NULL,
    regime TEXT NOT NULL,
    regime_confidence TEXT NOT NULL,
    similarity_status TEXT NOT NULL,
    similarity_sample_size INTEGER NOT NULL CHECK (similarity_sample_size >= 0),
    similarity_summary_json TEXT NOT NULL,
    probability_plus1_before_minus1 REAL,
    expected_return_24bar_r REAL,
    confidence TEXT NOT NULL,
    ood_status TEXT NOT NULL,
    ood_score REAL,
    score_status TEXT NOT NULL,
    abstention_reason TEXT,
    code_sha TEXT NOT NULL,
    forward_valid INTEGER NOT NULL CHECK (forward_valid IN (0, 1)),
    prediction_hash TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3_outcomes (
    forward_event_id TEXT PRIMARY KEY REFERENCES phase3_forward_events(forward_event_id),
    classification_label INTEGER CHECK (classification_label IN (0, 1)),
    return_6bar_r REAL,
    return_12bar_r REAL,
    return_24bar_r REAL,
    return_48bar_r REAL,
    mfe_r REAL,
    mae_r REAL,
    resolved_at_utc TEXT,
    outcome_observed_at_utc TEXT,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'RESOLVED', 'INCOMPLETE', 'EXPIRED', 'INVALID')),
    incomplete_reason TEXT,
    outcome_schema_version TEXT NOT NULL,
    outcome_hash TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3_health_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES phase3_forward_runs(run_id),
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    value_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3_evaluation_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES phase3_forward_runs(run_id),
    generated_at_utc TEXT NOT NULL,
    forward_sample_count INTEGER NOT NULL CHECK (forward_sample_count >= 0),
    collection_status TEXT NOT NULL,
    predictive_edge_status TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_phase3_events_run_time
    ON phase3_forward_events(run_id, event_timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_phase3_predictions_run
    ON phase3_predictions(forward_run_id, created_at_utc);
CREATE INDEX IF NOT EXISTS idx_phase3_outcomes_status
    ON phase3_outcomes(status, outcome_observed_at_utc);
CREATE INDEX IF NOT EXISTS idx_phase3_health_run
    ON phase3_health_events(run_id, created_at_utc);

-- Prediction/outcome evidence là append-only; correction phải là record riêng.
CREATE TRIGGER IF NOT EXISTS phase3_predictions_no_update
BEFORE UPDATE ON phase3_predictions
BEGIN
    SELECT RAISE(ABORT, 'phase3_predictions is append-only');
END;

CREATE TRIGGER IF NOT EXISTS phase3_predictions_no_delete
BEFORE DELETE ON phase3_predictions
BEGIN
    SELECT RAISE(ABORT, 'phase3_predictions is append-only');
END;

CREATE TRIGGER IF NOT EXISTS phase3_outcomes_no_update
BEFORE UPDATE ON phase3_outcomes
BEGIN
    SELECT RAISE(ABORT, 'phase3_outcomes is append-only');
END;

CREATE TRIGGER IF NOT EXISTS phase3_outcomes_no_delete
BEFORE DELETE ON phase3_outcomes
BEGIN
    SELECT RAISE(ABORT, 'phase3_outcomes is append-only');
END;

CREATE TRIGGER IF NOT EXISTS phase3_evaluation_snapshots_no_update
BEFORE UPDATE ON phase3_evaluation_snapshots
BEGIN
    SELECT RAISE(ABORT, 'phase3_evaluation_snapshots is append-only');
END;

CREATE TRIGGER IF NOT EXISTS phase3_evaluation_snapshots_no_delete
BEFORE DELETE ON phase3_evaluation_snapshots
BEGIN
    SELECT RAISE(ABORT, 'phase3_evaluation_snapshots is append-only');
END;
