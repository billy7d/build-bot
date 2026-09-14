CREATE TABLE IF NOT EXISTS strategy_versions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_strategy_version TEXT REFERENCES strategy_versions(id),
    git_commit TEXT,
    source_hash TEXT,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    strategy_version TEXT,
    audit_version TEXT,
    file_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    magic_number INTEGER,
    parameters_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(file_path, sha256)
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    strategy_version TEXT,
    audit_version TEXT,
    preset_id TEXT REFERENCES presets(id),
    symbol TEXT,
    timeframe TEXT,
    start_time TEXT,
    end_time TEXT,
    deposit REAL,
    leverage TEXT,
    history_quality TEXT,
    tick_model TEXT,
    purpose TEXT,
    fold_type TEXT NOT NULL CHECK (fold_type IN ('TRAIN', 'VALIDATION', 'OOS', 'FORWARD', 'SMOKE', 'UNKNOWN')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    parser_name TEXT,
    parser_version TEXT,
    strategy_version TEXT,
    audit_version TEXT,
    preset_id TEXT REFERENCES presets(id),
    experiment_id TEXT REFERENCES experiments(id),
    source_timezone TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    imported_at TEXT,
    error_message TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(sha256, parser_name, parser_version)
);

CREATE TABLE IF NOT EXISTS trading_episodes (
    episode_id TEXT PRIMARY KEY,
    source_artifact_id INTEGER NOT NULL REFERENCES source_artifacts(id),
    experiment_id TEXT REFERENCES experiments(id),
    strategy_version TEXT,
    audit_version TEXT,
    preset_id TEXT REFERENCES presets(id),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    source_time TEXT,
    source_timezone TEXT,
    timestamp_utc TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    episode_kind TEXT NOT NULL CHECK (episode_kind IN (
        'EXECUTION_CANDIDATE', 'EXECUTED_TRADE', 'FLAT_CANDIDATE',
        'BLOCKED_OPPORTUNITY', 'CONTROL_OPPORTUNITY',
        'SIMULTANEOUS_CONFLICT', 'PYRAMID_OPPORTUNITY', 'UNKNOWN'
    )),
    candidate_type TEXT NOT NULL CHECK (candidate_type IN ('BASE', 'PYRAMID', 'FLAT', 'BLOCKED', 'CONTROL', 'UNKNOWN')),
    candidate_exists INTEGER NOT NULL CHECK (candidate_exists IN (0, 1)),
    was_executed INTEGER NOT NULL CHECK (was_executed IN (0, 1)),
    execution_id TEXT,
    entry_candidate REAL,
    stop_candidate REAL,
    target_candidate REAL,
    planned_risk_r REAL,
    fold_type TEXT NOT NULL CHECK (fold_type IN ('TRAIN', 'VALIDATION', 'OOS', 'FORWARD', 'SMOKE', 'UNKNOWN')),
    raw_event_id TEXT NOT NULL,
    raw_fields_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_artifact_id, raw_event_id)
);

CREATE TABLE IF NOT EXISTS episode_features (
    episode_id TEXT PRIMARY KEY REFERENCES trading_episodes(episode_id) ON DELETE CASCADE,
    rsi REAL,
    atr14 REAL,
    atr_percent REAL,
    return_1 REAL,
    return_3 REAL,
    return_6 REAL,
    return_std_20 REAL,
    return_std_rank REAL,
    price_std_20 REAL,
    price_std_100 REAL,
    price_std_pct_20 REAL,
    std_ratio_20_100 REAL,
    price_z20 REAL,
    price_abs_z20 REAL,
    rsi_std_20 REAL,
    rsi_std_rank REAL,
    atr_return_std_ratio REAL,
    atr_return_std_rank REAL,
    feature_schema_version TEXT NOT NULL,
    feature_provenance TEXT NOT NULL,
    feature_timestamp_utc TEXT NOT NULL,
    raw_features_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    episode_id TEXT REFERENCES trading_episodes(episode_id),
    order_id TEXT,
    deal_id TEXT,
    entry_time TEXT,
    entry_price REAL,
    exit_time TEXT,
    exit_price REAL,
    volume REAL,
    desired_risk_money REAL,
    actual_risk_money REAL,
    spread_r REAL,
    slippage_r REAL,
    stop_loss REAL,
    take_profit REAL,
    exit_reason TEXT,
    net_profit REAL,
    commission REAL,
    swap REAL,
    result_r REAL
);

CREATE TABLE IF NOT EXISTS episode_outcomes (
    episode_id TEXT PRIMARY KEY REFERENCES trading_episodes(episode_id) ON DELETE CASCADE,
    resolved INTEGER NOT NULL CHECK (resolved IN (0, 1)),
    mfe_r REAL,
    mae_r REAL,
    hit_plus_1r_first TEXT,
    hit_minus_1r_first TEXT,
    forward_return_6h REAL,
    forward_return_12h REAL,
    forward_return_24h REAL,
    forward_return_48h REAL,
    bars_to_mfe INTEGER,
    bars_to_mae INTEGER,
    outcome_timestamp_utc TEXT,
    incomplete_reason TEXT,
    outcome_schema_version TEXT NOT NULL
);
