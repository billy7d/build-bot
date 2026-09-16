# Hướng dẫn agent vận hành build-bot

Đối với Phase 3 FORWARD, đọc theo thứ tự:

1. `docs/trading_agent/forward_ops/AGENT_TAKEOVER.md`
2. `docs/trading_agent/forward_ops/FORWARD_HANDOFF.md`
3. `docs/trading_agent/forward_ops/FORWARD_RUNBOOK.md`
4. `docs/trading_agent/forward_ops/RECOVERY.md` khi có sự cố dữ liệu hoặc máy.

Source checkout là immutable khi một run hoạt động. Runtime và handoff động phải
ở ngoài repository, mặc định chỉ là ví dụ được operator truyền bằng tham số.
Agent giám sát chỉ được đọc status/health, tạo snapshot, ghi incident và chạy
backup không phá hủy. Không được sửa model/bundle, đổi Git SHA, tạo authorization
hoặc run, cài/bật Scheduler, bật quyền giao dịch hay bắt đầu FORWARD.

Nếu `CURRENT_HANDOFF.md`, SQLite, ingest checkpoint, source identity, heartbeat
hoặc backup có mâu thuẫn, dừng với `TAKEOVER_BLOCKED`/`MERGE_READY=NO` và ghi
incident. Không giải quyết mâu thuẫn bằng cách xóa, reset, clean hoặc fabricate
record. `LIVE_EXECUTION_ENABLED=NO` và mọi execution authority phải giữ ở `NONE`.
