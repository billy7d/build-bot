-- Phase 3.1 forward campaign: gom nhiều FORWARD run cùng bundle thành một mẫu đánh giá.
-- Run vẫn bất biến; campaign chỉ là membership khai báo trước và coverage.

CREATE TABLE IF NOT EXISTS phase3_forward_campaigns (
    campaign_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL REFERENCES phase3_shadow_bundles(bundle_id),
    primary_source_schema TEXT NOT NULL,
    canonical_schema TEXT NOT NULL,
    canonicalizer_version TEXT NOT NULL,
    canonicalizer_fingerprint TEXT NOT NULL,
    window_start_utc TEXT NOT NULL,
    declared_at_utc TEXT NOT NULL,
    declaration_json TEXT NOT NULL,
    declaration_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3_forward_campaign_runs (
    campaign_id TEXT NOT NULL REFERENCES phase3_forward_campaigns(campaign_id),
    run_id TEXT NOT NULL REFERENCES phase3_forward_runs(run_id),
    attached_at_utc TEXT NOT NULL,
    attach_reason TEXT NOT NULL,
    PRIMARY KEY (campaign_id, run_id)
);

-- Một dòng mỗi run, cập nhật mỗi poll: khoảng thời gian collector thực sự đọc source.
CREATE TABLE IF NOT EXISTS phase3_forward_run_liveness (
    run_id TEXT PRIMARY KEY REFERENCES phase3_forward_runs(run_id),
    first_cycle_utc TEXT NOT NULL,
    last_cycle_utc TEXT NOT NULL,
    cycle_count INTEGER NOT NULL CHECK (cycle_count >= 1)
);

CREATE INDEX IF NOT EXISTS idx_phase3_campaign_runs_run
    ON phase3_forward_campaign_runs(run_id);
