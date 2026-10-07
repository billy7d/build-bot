-- Phase 3.1: observation đã bị REJECTED_SCHEMA do lỗi định dạng thời gian, nạp lại SAU thời điểm sự kiện.
-- Bảng này tách khỏi forward: không có prediction, không vào campaign, không tính forward_sample_count.

CREATE TABLE IF NOT EXISTS phase3_late_ingested_observations (
    source_forward_event_id TEXT PRIMARY KEY REFERENCES phase3_forward_events(forward_event_id),
    run_id TEXT NOT NULL REFERENCES phase3_forward_runs(run_id),
    source_observation_id TEXT NOT NULL,
    event_timestamp_utc TEXT NOT NULL,
    original_received_at_utc TEXT NOT NULL,
    late_ingested_at_utc TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    side TEXT NOT NULL,
    source_audit_family TEXT NOT NULL,
    source_event_type TEXT NOT NULL,
    bar_state TEXT NOT NULL,
    build_valid INTEGER NOT NULL,
    canonical_opportunity_id TEXT,
    raw_payload_sha256 TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    forward_eligible INTEGER NOT NULL DEFAULT 0 CHECK (forward_eligible = 0),
    ingest_class TEXT NOT NULL DEFAULT 'LATE_NOT_FORWARD' CHECK (ingest_class = 'LATE_NOT_FORWARD')
);

CREATE INDEX IF NOT EXISTS idx_phase3_late_ingested_run
    ON phase3_late_ingested_observations(run_id);
