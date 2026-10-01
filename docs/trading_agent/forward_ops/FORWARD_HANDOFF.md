# Persistent Forward Handoff Contract

Handoff động nằm ngoài Git, dưới `OpsRoot`:

```text
CURRENT_HANDOFF.md
current_state.json
machine_manifest.json
latest_health.json
backup_status.json
logs/operator_log.jsonl
logs/incident_log.jsonl
runs/<run-id>/handoff-snapshots/
```

`current_state.json` là snapshot, không phải database độc lập. Nguồn sự thật là
SQLite rows đã commit, `phase3_ingest_offsets`, source identity/EOF và heartbeat
PID. Snapshot được ghi atomic nên agent mới không đọc file đang ghi dở.

Tạo snapshot:

```powershell
.\scripts\phase3\handoff_snapshot.ps1 `
  -RuntimeConfig 'E:\build-bot-runtime\phase3\config\forward.json' `
  -OpsRoot 'E:\build-bot-ops\phase3'
```

Snapshot phải trả lời: collector đang chạy/dừng, run ID, code SHA, bundle/model/
index, MT5 source status, checkpoint/offset, canonical/raw/prediction/resolved
counts, backup cuối hợp lệ, incident chưa xử lý, quyền của agent và bước kế tiếp.
`forward_sample_count` không được trình bày như resolved labels.

Snapshot có thể chạy khi collector đang hoạt động; nó không giành collector lock
và không restart collector. Nếu generator lỗi, collector độc lập vẫn tiếp tục;
health/incident phải cho biết `HANDOFF_STALE` và agent không được đọc stale state
như bằng chứng mới.

Agent takeover đọc `AGENTS.md`, tài liệu này và `CURRENT_HANDOFF.md`, sau đó chạy
`status-runtime`, `ops-health`, `takeover-check` ở chế độ read-only. Agent B phải
đối chiếu run ID/PID/offset/source identity/SHA/bundle/backup/incidents. Mismatch
trả `TAKEOVER_BLOCKED`, ghi incident và dừng; không sửa file authoritative.
