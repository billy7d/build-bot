-- Bổ sung linkage canonical mà không sửa các migration lịch sử.
ALTER TABLE trading_episodes ADD COLUMN canonical_opportunity_id TEXT;

CREATE INDEX IF NOT EXISTS idx_trading_episodes_canonical_opportunity
    ON trading_episodes(canonical_opportunity_id);
