-- Bổ sung spread_r cho database đã được tạo từ bốn migration Phase 1 đầu tiên.
ALTER TABLE episode_features ADD COLUMN spread_r REAL;
