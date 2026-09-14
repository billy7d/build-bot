CREATE TABLE IF NOT EXISTS audit_versions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    audit_type TEXT NOT NULL,
    base_strategy_version TEXT,
    parent_audit_version TEXT REFERENCES audit_versions(id),
    git_commit TEXT,
    source_hash TEXT,
    mode TEXT NOT NULL,
    execution_authority TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_strategy ON source_artifacts(strategy_version);
CREATE INDEX IF NOT EXISTS idx_source_audit ON source_artifacts(audit_version);
CREATE INDEX IF NOT EXISTS idx_experiment_fold ON experiments(fold_type);
