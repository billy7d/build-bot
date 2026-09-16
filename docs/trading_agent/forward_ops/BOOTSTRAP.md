# Fresh Windows Forward Node Bootstrap

Tài liệu này mô tả việc dựng node mới. Nó không tạo authorization, không tạo
FORWARD run, không cài Scheduler và không bật giao dịch.

## Ba vùng dữ liệu

- Source: checkout đúng `approved_git_sha`, chỉ đọc khi run hoạt động.
- Runtime: SQLite, artifact đã đóng băng, telemetry, checkpoint, heartbeat và log.
- Operations: handoff, health, backup, incident và audit log.

Không đưa runtime hoặc handoff động vào source. Các path trong ví dụ chỉ là giá
trị truyền vào, script không hardcode ổ đĩa:

```powershell
.\scripts\phase3\bootstrap_forward_node.ps1 `
  -InstallRoot 'E:\build-bot' `
  -RuntimeRoot 'E:\build-bot-runtime\phase3' `
  -OpsRoot 'E:\build-bot-ops\phase3' `
  -PackagePath 'D:\transfer\phase3-forward-node-package' `
  -ExpectedGitSha '<full-approved-sha>' `
  -ExpectedTrustedManifestDigest '<manifest-sha256-from-trusted-channel>'
```

Package phải được tạo từ các artifact thật bằng `package-forward-node`. Model
bundle và historical similarity index thiếu hoặc sai fingerprint là lỗi dừng,
không được retrain hay tạo file giả. `CHECKSUMS.sha256` chỉ chứng minh tính
toàn vẹn bên trong package. Trước khi dùng package production, operator phải
lấy `manifest_sha256` từ kênh tin cậy ngoài package và truyền thêm
`-ExpectedTrustedManifestDigest` cho bootstrap; không dùng giá trị nằm trong
package để tự xác nhận chính nó. Package `TEST_ONLY` được phép verify không có
detached attestation nhưng không phải bằng chứng provenance production.

Bootstrap kiểm tra Windows, Git, Python, PowerShell và quyền ghi; clone vào
InstallRoot chỉ khi source chưa có. Nếu InstallRoot đã là repo nhưng HEAD sai,
bootstrap dừng, không reset/clean/checkout đè. Runtime đã có authorization hoặc
current run cũng làm bootstrap dừng để operator review.

Readiness thành công có nghĩa:

```text
BOOTSTRAP_STATUS=PASS
FORWARD_AUTHORIZATION=NOT_CREATED
FORWARD_RUN_ID=NOT_CREATED
SCHEDULER=NOT_INSTALLED_OR_DISABLED
LIVE_EXECUTION_ENABLED=NO
MT5_SOURCE_STATUS=WAITING_FOR_FIRST_REAL_RECORD
ACTIVATION_READY=NO
```

Sau bootstrap, kiểm tra `bootstrap_readiness.json`, `CURRENT_HANDOFF.md` và
`latest_health.json`. Chưa có primary JSONL thật không phải lỗi bootstrap và
không được vượt qua bằng synthetic JSONL.

## MT5 tách khỏi bootstrap

Cài terminal bằng tay, đăng nhập broker bằng tay và không copy account database
từ máy monitor. Dùng `mt5_preflight.ps1` để kiểm tra executable, data directory,
EX5/preset checksum, FILE_COMMON và journal evidence. Chỉ khi operator xác nhận
server/account, market data BTCUSD/H1 và first real opportunity record mới có
thể xem preflight là PASS; công cụ không tự mở terminal hay tạo record.
