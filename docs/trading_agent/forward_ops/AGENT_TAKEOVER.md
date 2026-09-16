# Agent Takeover Checklist

Agent B không cần lịch sử chat. Thực hiện theo checklist này và ghi acknowledgement
vào `operator_log.jsonl`.

1. Đọc root `AGENTS.md`, `FORWARD_HANDOFF.md` và `RECOVERY.md`.
2. Đọc `CURRENT_HANDOFF.md`, `current_state.json`, `latest_health.json`,
   `backup_status.json` và incident tail.
3. Chạy `status-runtime`, `ops-health` và `takeover-check`; chỉ dùng read-only.
4. Đối chiếu run ID, collector PID/heartbeat, Git SHA, bundle/model/index,
   source identity, byte offset/EOF và backup cuối hợp lệ.
5. Xác nhận `execution_authority=NONE`, `trade_control_authority=NONE`,
   `LIVE_EXECUTION_ENABLED=NO`, authorization/run/scheduler đúng trạng thái.
6. Nếu khớp, ghi:

   ```powershell
   python -m agent.phase3 takeover-ack `
     --ops-root 'E:\build-bot-ops\phase3' `
     --agent-id '<agent-id>'
   ```

7. Nếu bất kỳ mâu thuẫn nào, không acknowledgement thành công; giữ
   `TAKEOVER_BLOCKED`, ghi incident và chờ operator phê duyệt.

Takeover không restart collector và không đổi run ID/PID/offset. Handover động
không được phụ thuộc vào Codex, browser hay agent A.

## Quyền hạn

| Hành động | Agent giám sát |
| --- | --- |
| Đọc status/health/log và tạo snapshot | Được phép |
| Backup không phá hủy, ghi incident | Được phép |
| Sửa model/bundle/execution logic | Không |
| Tạo authorization hoặc FORWARD run | Không |
| Đổi SHA khi run hoạt động | Không |
| Cài/bật Scheduler hoặc giao dịch | Không |
| Restore đè runtime/chuyển máy/xóa run | Cần phê duyệt riêng |
