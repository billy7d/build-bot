# Incident Response

Agent ghi `incident_log.jsonl`, không sửa dữ liệu authoritative để làm mất
triệu chứng. Mỗi incident cần thời điểm UTC, severity, code, evidence path và
next action. Các nhóm thường gặp:

- `HEARTBEAT_CRITICAL_STALE` hoặc PID mất: không restart vô điều kiện; kiểm tra
  OS lock, process, checkpoint và last backup trước.
- `PRIMARY_SOURCE_IDENTITY_MISMATCH`, truncate hoặc offset vượt EOF: dừng
  ingest/resume, giữ file và backup, không đọc lại từ byte 0.
- `SQLITE_INTEGRITY_FAILED`: cô lập bản DB, không overwrite DB đang chạy; verify
  backup và restore isolated.
- `BACKUP_INVALID` hoặc disk thấp: ghi incident, tạo bản backup mới ở vị trí
  khác nếu an toàn, không xóa bản valid cuối.
- MT5 GUI/account/session: chạy `mt5-preflight`, đọc journal và xác minh broker
  bằng chứng; primary file không chứng minh được broker connection.
- Handoff generator lỗi: đánh dấu `HANDOFF_STALE`; collector vẫn là process độc
  lập, agent không đoán số liệu từ snapshot cũ.

Các trạng thái `UNKNOWN` cần được báo cáo là thiếu bằng chứng. Không tự đổi model,
bundle, cutoff, source, Git SHA, risk, execution logic hoặc quyền giao dịch.
