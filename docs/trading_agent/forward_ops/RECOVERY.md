# Recovery và Migration

## Restore isolated

Luôn verify trước, sau đó restore vào thư mục trống isolated:

```powershell
python -m agent.phase3 verify-forward-backup --backup-path 'D:\backup\<id>'
python -m agent.phase3 restore-forward-backup `
  --backup-path 'D:\backup\<id>' `
  --target-root 'D:\restore\phase3-evidence'
```

Restore không overwrite runtime đang chạy, kiểm tra SQLite integrity/foreign
keys và giữ checkpoint/raw prefix để đối chiếu. Bản restore không tự tạo config
active, authorization hay run.

## Cùng máy, cùng source identity

Chỉ operator có phê duyệt riêng mới thực hiện resume. Phải xác minh code SHA,
bundle/model/index, authorization, source identity, EOF và offset trước; offset
không được vượt EOF. Các rows đã commit không được ingest lại.

## Máy khác

Path là một phần source identity và authorization hiện tại, nên không âm thầm
chuyển run. Dùng migration plan:

```powershell
python -m agent.phase3 plan-forward-migration `
  --backup-path 'D:\backup\<id>' `
  --new-install-root 'E:\build-bot' `
  --new-runtime-root 'E:\build-bot-runtime\phase3' `
  --output 'E:\build-bot-ops\phase3\migration-plan.json'
```

Contract bắt buộc:

```text
OLD_RUN=STOPPED_OR_FAILED
NEW_RUN=REQUIRES_NEW_AUTHORIZATION
CROSS_RUN_CONTINUITY=NOT_CLAIMED
AUTHORIZATION_REUSE=NOT_ALLOWED
```

Giữ run cũ để đánh giá riêng, không cộng hai run thành một chuỗi forward liên
tục. Nếu backup hỏng/thiếu raw prefix, restore bị từ chối.
