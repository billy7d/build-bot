# Forward Node Daily Runbook

Collector là process độc lập với Codex/ChatGPT/browser. Agent chỉ quan sát và
ghi evidence. Không coi file JSONL còn tồn tại là bằng chứng broker còn kết nối.

## Read-only checks

```powershell
python -m agent.phase3 status-runtime `
  --runtime-config 'E:\build-bot-runtime\phase3\config\forward.json'
python -m agent.phase3 ops-health `
  --runtime-config 'E:\build-bot-runtime\phase3\config\forward.json' `
  --ops-root 'E:\build-bot-ops\phase3'
python -m agent.phase3 handoff-snapshot `
  --runtime-config 'E:\build-bot-runtime\phase3\config\forward.json' `
  --ops-root 'E:\build-bot-ops\phase3'
```

Health theo dõi PID/heartbeat, OS lock, source identity, size/offset/backlog,
last event/prediction, raw/canonical/duplicate counts, predictions, resolved
outcomes, SQLite integrity, disk free và backup cuối. Ngưỡng disk/heartbeat có
thể truyền bằng CLI. Trạng thái hợp lệ là `HEALTHY`, `WARNING`, `CRITICAL` hoặc
`UNKNOWN`; không tự sửa khi cảnh báo.

## Backup

```powershell
.\scripts\phase3\backup_forward_runtime.ps1 `
  -RuntimeConfig 'E:\build-bot-runtime\phase3\config\forward.json' `
  -OpsRoot 'E:\build-bot-ops\phase3'
```

Backup dùng SQLite online backup API, giữ raw source đến đúng committed offset,
ghi source identity/size/offset/checksum/timestamp và kiểm tra integrity. Nếu
không chứng minh được consistency thì kết quả là `BACKUP_INVALID`, không dùng để
restore. Cần cấu hình thêm bản mã hóa ở thiết bị/vị trí khác; backup cùng ổ đĩa
không đủ cho mất máy.

Không chạy `prepare-forward`, `start-forward`, `resume-forward` hoặc các script
Scheduler trong phạm vi PR vận hành này. Authorization và run phải do gate/phê
duyệt riêng trong tương lai.
