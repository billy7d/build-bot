# Machine 1 — Báo cáo kích hoạt thu dữ liệu forward Phase 3.1 (2026-10-02)

Báo cáo theo §9 của `docs/trading_agent/phase3/MACHINE1_FORWARD_COLLECTION_HANDOFF_20261001.md`.
Không chứa outcome, hit rate, Brier/AUC, nội dung JSONL, CSV giao dịch, account/server/IP hay credential.

## Định danh run

| Mục | Giá trị |
|---|---|
| AUTHORIZED_SHA | `b429704a92a89f46cb932d16cc25328ac4587a85` |
| authorization_id | `p3-auth-580b12980ad0f2b41aa11de8` |
| run_id | `P3-FWD-20261002T043335Z-b429704a92a8` |
| Thời điểm start (UTC) | 2026-10-02T04:33:35Z (lần start đầu), task khởi động lại 04:35:5xZ cùng run |
| Hệ thống | V26 (magic 26072626, preset 83). V63 chưa bật collector |
| Bundle | `p3-bundle-577e5dfd0702c52c8f5318063703dd616a633704444ba5371e1c74e6dc080c6a` |
| Offset bind ban đầu | 2778 byte (cuối file opportunity tại thời điểm start) |

## Đường dẫn dùng trên máy 1 (khác tài liệu)

- Checkout runtime: `D:\Trading\buildbot` (thay `E:\build-bot`)
- Runtime root: `D:\Trading\build-bot-runtime\phase3` (thay `E:\build-bot-runtime\phase3`)
- Clone báo cáo: `D:\Trading\build-bot-reports`
- Terminal V26: `D:\Trading\MT5-V26`; V63: `D:\Trading\MT5-V63` (hai terminal không portable, data folder trong `%APPDATA%\MetaQuotes\Terminal\`)
- Python: 3.12.1 (`py -3`)

## Hash

| Mục | Giá trị |
|---|---|
| Blob source EA | `49f924e3927d8cb3ee1ee4b7369fd8294b030c9f` (khớp) |
| Preset 83 SHA-256 | `b5ead1a5e54d3ca2f473c04d8c01c5cb9e2508e339b1793dc67f8f00d96b2abf` (khớp) |
| Preset 84 SHA-256 | `07ecf4059efd8a05224e6e8536f2273aebc0fadecf16d22710ec69a7c665dfac` (khớp) |
| `.ex5` V26 (compile 0 errors, 0 warnings) | `18df4f908bfe8ebb274bc05861e85b32b6e4209b4608486766581dc8ee5929f1` |
| `.ex5` V63 (compile 0 errors, 0 warnings) | `6071da4c314da34a87a71747c2a6433530c77aa0de427568d58111d368598971` |
| `model_bundle.json` | `36bcdbeb69694f45ec46d83a2c946dbebf935db3f2046b1684cead9655606c31` (khớp) |
| `history_index.json` | `f84d36c48df3269f268b41f0c6102098ae17698dfe88cc643d17b8ae982257f8` (khớp) |

## Kết quả §4 và §7

- Tracked tree sạch, `main` = `origin/main` = `b429704`.
- `compileall` PASS; `unittest discover -s agent/tests`: 95/95 OK (Python 3.12.1).
- `validate-bundle`: `BUNDLE_VALID`, bundle id như trên.
- Gate (chạy trên máy 1 tại AUTHORIZED_SHA): replay/parity 27/27 (`test_phase3`, `test_phase3_canonical`), `test_phase3_1` 8/8, smoke `m1-smoke-202610020350` = `SHADOW_READY` (integrity ok, foreign key ok), `execution_api_path_count=0`. Bốn gate đều PASS.

## Trạng thái runtime (sau khi khởi động lại task)

Đọc từ `state\heartbeat.json` (đã bỏ đường dẫn có tên user):

```json
{
  "collector_status": "RUNNING",
  "telemetry_status": "CONNECTED",
  "execution_mode": "NONE",
  "live_execution_enabled": false,
  "initial_source_offset": 2778,
  "current_source_offset": 2778,
  "git_sha": "b429704a92a89f46cb932d16cc25328ac4587a85",
  "run_id": "P3-FWD-20261002T043335Z-b429704a92a8"
}
```

Output `status-runtime --json` không đưa vào được, xem lỗi 3 bên dưới.

Task `BuildBot-Phase3-Forward`: state `Running`, trigger AtLogOn, logon type Interactive, run level Limited, `-ExecutionTimeLimit 0`, restart 3 lần cách 1 phút.

## Sai lệch so với tài liệu

1. **Đường dẫn ổ D:** theo chỉ định của operator.
2. **Artifact §3** đã có sẵn trong `assets\` với SHA-256 đúng, không chép lại.
3. **`start-forward` / `resume-forward` lỗi** `AttributeError: 'Namespace' object has no attribute 'authorization'` tại `agent/phase3/cli.py` (`_forward_collector`): tham số `--authorization` khai báo với `default=argparse.SUPPRESS`. Cách xử lý: truyền `--authorization <đường dẫn>` rõ ràng. Không sửa code.
4. **`scripts/phase3/install_forward_task.ps1` lỗi** trên Windows 11: `-LogonType InteractiveToken` không hợp lệ (enum đúng là `Interactive`). Task được đăng ký thủ công với cùng thiết lập, thêm `-Authorization` cho runner (runner không tự truyền `--authorization` khi chưa có tham số này, nên task sẽ lỗi nếu thiếu).
5. **`status-runtime` giết collector.** `agent/phase3/forward.py` `_pid_alive` gọi `os.kill(pid, 0)`; trên Windows lệnh này gọi TerminateProcess. Lần chạy `status-runtime` đầu tiên (lúc có collector chạy) làm collector thoát (exit 0, 04:35:12Z) và `status-runtime` tự lỗi. Task được khởi động lại, tiếp tục cùng run và cùng offset. Lúc đó chưa có bản ghi mới nên không mất mẫu. **Không chạy `status-runtime` trên Windows khi collector đang chạy** cho tới khi sửa. Theo dõi bằng `state\heartbeat.json`.
6. Lần gắn EA đầu tiên nhầm bản cũ (`Experts\Advisors\Mentor_RSI_MTF_v1`, build tháng 7, không có cờ Phase 3) và nạp nhầm preset giữa hai terminal. Đã sửa; log xác nhận V26 magic 26072626 và V63 magic 26072663, mỗi bên ghi đúng file `Mentor_RSI_MTF_<magic>_BTCUSD_H1.jsonl`.
7. Hai file rỗng `Mentor_RSI_MTF_26062901_BTCUSD_M15.jsonl` (telemetry và opportunities) là rác từ lần gắn sai, để nguyên, không xóa.
8. Archive CSV V63 cũ: 3 file `Mentor_RSI_MTF_{diag,forward,shadow_signals}.csv` đã chuyển (không xóa) vào `MQL5\Files\archive-20261001` của V63. Archive V26 có sẵn từ trước.
9. File opportunity V26 đã có 2 bản ghi lúc EA nạp lại (11:19:46 giờ máy), trước thời điểm bind. Theo thiết kế chúng không tính là mẫu forward.
10. V63 collector: chưa bật, chờ quyết định operator (bước tùy chọn §8).

## Việc còn lại

- Operator quyết định sửa lỗi 3 và 5 bằng PR riêng; sau khi merge phải `prepare-forward` lại và khởi động lại collector (HEAD đổi).
- Operator quyết định bật collector V63.

## Cập nhật 2026-10-03: sự cố heartbeat và run mới

- **PR #7 đã merge** vào `main` (`82f26986832e7bb92d4759e83c37c4de767bcdeb`): sửa `--authorization`, `status-runtime` không còn giết collector, installer dùng `-LogonType Interactive`. Checkout runtime đã `pull --ff-only` về commit này khi cả hai collector đang dừng.
- **Run V26 cũ `P3-FWD-20261002T043335Z-b429704a92a8` bị FAILED** lúc 2026-10-02T17:12:32Z: `[WinError 5] Access is denied` khi collector đổi tên `state\heartbeat.json.tmp` đè `heartbeat.json`. Nguyên nhân khả dĩ nhất là task watchdog (do agent cài) đọc `heartbeat.json` mỗi 2 phút bằng `Get-Content`, không chia sẻ quyền xóa/đổi tên. Chưa chứng minh. Run FAILED không resume được (`failed FORWARD run cannot be resumed`); DB và state được giữ nguyên làm bằng chứng.
- **Khoảng trống dữ liệu V26:** collector không chạy từ 17:12Z đến khoảng 06:09Z (khoảng 13 giờ). Các bản ghi opportunity xuất hiện trong khoảng này vẫn nằm trong file nhưng không thuộc run mới (run mới bind ở cuối file lúc start), nên **không tính là mẫu forward**.
- **Watchdog đã sửa**: đọc heartbeat với `FileShare.ReadWrite | Delete`. Lưu ý: watchdog chỉ khởi động lại khi `collector_status=RUNNING` mà heartbeat cũ quá 180 giây; trạng thái FAILED vẫn cần operator xử lý.
- **Gate evidence chạy lại tại SHA mới**: 96/96 unit test, 27/27 replay/parity, 9/9 `test_phase3_1`, smoke `m1-smoke-202610030608` = `SHADOW_READY`, integrity ok.
- **Run mới (start 2026-10-03):**
  - V26: `P3-FWD-20261003T060939Z-82f26986832e`, bind offset 11138, task `BuildBot-Phase3-Forward`.
  - V63: `P3-FWD-20261003T060928Z-82f26986832e`, bind offset 5582 (4 bản ghi hợp lệ trước thời điểm bind), task `BuildBot-Phase3-Forward-V63`, runtime root `D:\Trading\build-bot-runtime\phase3-v63`.
  - Cả hai: `RUNNING`, `CONNECTED`, `execution_mode=NONE`, `live_execution_enabled=false`, authorized SHA `82f26986832e7bb92d4759e83c37c4de767bcdeb`.
- **Authorization:** V63 `p3-auth-15cdc6e01fd9373d61502627`; V26 có authorization mới tại cùng SHA.
- Collector V63 được bật theo chỉ đạo của operator ngày 2026-10-02/03; file opportunity V63 có bản ghi đầu tiên trong khoảng 2026-10-03 (giờ máy sáng).
