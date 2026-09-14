-- Phase 2 is additive.  Phase 1 audit tables are intentionally untouched.

CREATE TABLE IF NOT EXISTS feature_sets (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    dataset_fingerprint TEXT NOT NULL,
    config_fingerprint TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    fit_scope TEXT NOT NULL CHECK (fit_scope IN ('TRAIN_ONLY', 'TRAIN_VALIDATION', 'NONE')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_opportunities (
    canonical_opportunity_id TEXT PRIMARY KEY,
    timestamp_utc TEXT NOT NULL,
    symbol TEXT,
    timeframe TEXT,
    side TEXT,
    strategy_version TEXT,
    observation_count INTEGER NOT NULL CHECK (observation_count >= 1),
    feature_status TEXT NOT NULL CHECK (feature_status IN ('VALID', 'PARTIAL', 'CONFLICT', 'INSUFFICIENT')),
    features_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    labels_json TEXT NOT NULL,
    field_status_json TEXT NOT NULL,
    audit_versions_json TEXT NOT NULL,
    episode_ids_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_features (
    canonical_opportunity_id TEXT NOT NULL REFERENCES canonical_opportunities(canonical_opportunity_id) ON DELETE CASCADE,
    feature_set_version TEXT NOT NULL REFERENCES feature_sets(version),
    normalized_vector_json TEXT NOT NULL,
    output_names_json TEXT NOT NULL,
    missing_json TEXT NOT NULL,
    feature_status TEXT NOT NULL,
    feature_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (canonical_opportunity_id, feature_set_version)
);

CREATE TABLE IF NOT EXISTS phase2_splits (
    canonical_opportunity_id TEXT NOT NULL REFERENCES canonical_opportunities(canonical_opportunity_id) ON DELETE CASCADE,
    split_version TEXT NOT NULL,
    split TEXT NOT NULL CHECK (split IN ('TRAIN', 'VALIDATION', 'OOS', 'FORWARD', 'UNKNOWN')),
    timestamp_utc TEXT NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (canonical_opportunity_id, split_version)
);

CREATE TABLE IF NOT EXISTS regime_assignments (
    canonical_opportunity_id TEXT NOT NULL REFERENCES canonical_opportunities(canonical_opportunity_id) ON DELETE CASCADE,
    regime_version TEXT NOT NULL,
    trend_state TEXT NOT NULL,
    volatility_state TEXT NOT NULL,
    liquidity_state TEXT NOT NULL,
    composite_regime TEXT NOT NULL,
    confidence TEXT NOT NULL,
    reason TEXT,
    source_reported_regime TEXT,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (canonical_opportunity_id, regime_version)
);

CREATE TABLE IF NOT EXISTS similarity_runs (
    run_id TEXT PRIMARY KEY,
    similarity_version TEXT NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    config_json TEXT NOT NULL,
    query_count INTEGER NOT NULL,
    no_opinion_count INTEGER NOT NULL,
    temporal_leakage_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS similarity_neighbors (
    run_id TEXT NOT NULL REFERENCES similarity_runs(run_id) ON DELETE CASCADE,
    query_opportunity_id TEXT NOT NULL REFERENCES canonical_opportunities(canonical_opportunity_id) ON DELETE CASCADE,
    neighbor_opportunity_id TEXT NOT NULL REFERENCES canonical_opportunities(canonical_opportunity_id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank >= 1),
    distance REAL NOT NULL,
    neighbor_timestamp_utc TEXT NOT NULL,
    neighbor_regime TEXT,
    neighbor_side TEXT,
    historical_outcome_json TEXT NOT NULL,
    PRIMARY KEY (run_id, query_opportunity_id, rank)
);

CREATE TABLE IF NOT EXISTS model_registry (
    model_version TEXT PRIMARY KEY,
    model_type TEXT NOT NULL,
    feature_set_version TEXT NOT NULL,
    split_version TEXT NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    fit_ids_json TEXT NOT NULL,
    calibration_fit_ids_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    model_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_predictions (
    model_version TEXT NOT NULL REFERENCES model_registry(model_version) ON DELETE CASCADE,
    canonical_opportunity_id TEXT NOT NULL REFERENCES canonical_opportunities(canonical_opportunity_id) ON DELETE CASCADE,
    split TEXT NOT NULL,
    p_plus_1r_before_minus_1r REAL,
    expected_r_24bar REAL,
    regime TEXT,
    similarity_sample_size INTEGER,
    model_confidence TEXT NOT NULL,
    data_quality TEXT NOT NULL,
    score_status TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (model_version, canonical_opportunity_id)
);

CREATE INDEX IF NOT EXISTS idx_phase2_canonical_timestamp
    ON canonical_opportunities(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_phase2_features_version
    ON canonical_features(feature_set_version);
CREATE INDEX IF NOT EXISTS idx_phase2_splits_split
    ON phase2_splits(split_version, split, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_phase2_regime_version
    ON regime_assignments(regime_version, composite_regime);
CREATE INDEX IF NOT EXISTS idx_phase2_similarity_query
    ON similarity_neighbors(run_id, query_opportunity_id);
CREATE INDEX IF NOT EXISTS idx_phase2_predictions_split
    ON model_predictions(model_version, split);
