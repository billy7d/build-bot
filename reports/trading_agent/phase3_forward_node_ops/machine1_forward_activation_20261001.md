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

## Cập nhật 2026-10-04: lỗi heartbeat lặp lại, PR #8 và run mới

- **Cả hai run ngày 2026-10-03 đều FAILED:**
  - V63 `P3-FWD-20261003T060928Z-82f26986832e` lúc 14:32:33Z với `[WinError 5] Access is denied` khi đổi tên `heartbeat.json`. Lỗi lặp lại dù watchdog đã đọc file với delete-share, nên watchdog không phải (hoặc không chỉ là) nguyên nhân. Nghi phần mềm quét file (Defender/indexer) giữ file ngắn hạn; chưa kiểm chứng.
  - V26 `P3-FWD-20261003T060939Z-82f26986832e`: heartbeat ngừng khoảng 09:38Z trong trạng thái RUNNING, DB ghi run FAILED. Watchdog khởi động lại lúc 09:42:32Z (`heartbeat_age=245s`) nhưng bị `failed FORWARD run cannot be resumed`. Lý do gốc không được lưu (DB không có cột lỗi, heartbeat bị ghi đè khi watchdog thử lại); phù hợp với cùng lỗi ghi heartbeat.
- **Khoảng trống dữ liệu:** V26 không có collector từ khoảng 09:38Z ngày 03/10 đến 14:53Z ngày 04/10; V63 từ 14:32Z ngày 03/10 đến 14:53Z ngày 04/10. Bản ghi trong các khoảng này vẫn nằm trong file nhưng không thuộc run nào, nên không tính là mẫu forward.
- **PR #8 đã merge** (`a939c4485161b6a9f84716a73659844002c4af9b`): `_atomic_json_write` thử lại việc đổi tên khi gặp `PermissionError` (backoff tổng khoảng 6 giây) trước khi fail.
- **Gate chạy lại tại SHA mới:** 98/98 unit test, 27/27 replay/parity, 11/11 `test_phase3_1`, `BUNDLE_VALID`, smoke `m1-smoke-202610041453` = `SHADOW_READY`.
- **Run mới (2026-10-04):**
  - V26: `P3-FWD-20261004T145311Z-a939c4485161`, authorization `p3-auth-c5711939ac85f87236e1e532`, bind offset 15305.
  - V63: `P3-FWD-20261004T145323Z-a939c4485161`, authorization `p3-auth-a232deb73f2283513c49233a`, bind offset 9748.
  - `status-runtime --json` (an toàn sau PR #7): cả hai `persistent_runtime_status=RUNNING`, `telemetry_status=CONNECTED`, `execution_mode=NONE`, `live_execution_enabled=false`.
- **Khuyến nghị operator:** cân nhắc thêm ngoại lệ Windows Defender cho `D:\Trading\build-bot-runtime` (cài đặt bảo mật, operator tự quyết).

## Cập nhật 2026-10-05: campaign và resilience (migration 010)

- **SHA mới:** `258b550384ebed08c6e0516b951a55d38d6a906f`. Checkout runtime `pull --ff-only` khi cả hai collector đã dừng.
- **Trước khi nâng cấp:** hai run ngày 04/10 bị watchdog khởi động lại hai lần trong ngày 05/10 (16:32Z và 17:30Z), mỗi lần cả V26 và V63 cùng im 3,5–4,5 phút rồi tiếp tục cùng run và offset, không mất bản ghi. Nguyên nhân (một thứ bên ngoài ngắt tiến trình) chưa rõ.
- **Dừng và sao lưu:** watchdog được tắt tạm khi bảo trì. `stop_forward_task.ps1` lỗi cú pháp trên Windows PowerShell 5.1 (`The term 'if' is not recognized`) nhưng vẫn disable task và tiến trình đã dừng. Run chỉ sang `STOPPED` sau khi `resume-forward` chạy ngắn rồi nhận `stop-forward` (collector xóa stop marker khi bắt đầu, nên marker phải ghi sau khi nó chạy). DB sao lưu bằng copy sang `evidence\pre-010-20261005.sqlite` (SHA-256 khớp bản gốc).
- **Campaign:** `v26-bundle577e-c1` và `v63-bundle577e-c1`, `window_start_utc=2026-10-02T00:00:00Z`, `campaign-declare` thành công, `excluded` rỗng.
- **Membership (V26):** 3 run cũ (`...20261002T043335Z`, `...20261003T060939Z`, `...20261004T145311Z`) và run mới. **V63:** 2 run cũ (`...20261003T060928Z`, `...20261004T145323Z`) và run mới. Run cũ có `coverage_basis=ESTIMATED_PRE_LIVENESS` nên coverage bị ước thấp (khoảng trống liệt kê bên dưới gồm cả thời gian collector thực ra đang chạy).
- **Sample count:** `forward_sample_count=0`, `canonical_row_count=0`, `cross_run_duplicate_count=0` cho cả hai (chưa có outcome resolve).
- **Gaps theo `campaign-status` (giây):** V26 92164 (02→03/10), 117811 (03→04/10), 96253 (04→05/10); V63 117834 (03→04/10), 96253 (04→05/10).
- **Gate chạy lại tại SHA mới:** 107/107 unit test, 27/27 replay/parity, 11/11 `test_phase3_1`, `BUNDLE_VALID`, smoke `m1-smoke-202610051737` = `SHADOW_READY`.
- **Run mới:** V26 `P3-FWD-20261005T173724Z-258b550384eb` (authorization `p3-auth-ebd770e243900dea69a61b8e`, bind offset 19471); V63 `P3-FWD-20261005T173736Z-258b550384eb` (authorization `p3-auth-734998ced2bf844840b5b9e0`, bind offset 13913). Offset bind trùng offset lúc dừng nên không mất bản ghi opportunity trong lúc bảo trì.
- **Kiểm tra:** `status-runtime`: cả hai `RUNNING`, `CONNECTED`, `campaign_id` đúng, `last_failure` rỗng, `execution_mode=NONE`.
- **Sai lệch:** task scheduled hiện có được bật lại (không cài mới); watchdog bật lại sau khi xong.

## Cập nhật 2026-10-07: lỗi định dạng thời gian MT5 (không có mẫu forward nào được ghi nhận trước đó)

- **Phát hiện:** V26 và V63 `RUNNING`/`CONNECTED` nhưng `raw_observation_count=0`, `forward_sample_count=0`. Bảng `phase3_forward_events` ghi mọi bản ghi opportunity với `validation_status=REJECTED_SCHEMA`, lý do `invalid UTC timestamp: '2026.10.07 05:00:00Z'`. EA ghi thời gian bằng `TimeToString(...) + "Z"` (dạng `YYYY.MM.DD HH:MM:SSZ`), còn `parse_utc_timestamp` chỉ nhận ISO-8601.
- **Phạm vi:** toàn bộ bản ghi từ 2026-10-02 đến lúc sửa: **V26 15, V63 7 bản ghi bị loại**, 0 bản ghi được nhận. Payload gốc và hash được giữ nguyên trong DB, đã sao lưu bản DB trước khi sửa (`evidence\pre-timestampfix-20261007.sqlite`).
- **Sửa:** PR #10 (`fix: accept MT5 UTC timestamps in forward ingestion`), merge vào `main` (`44f045bf22b9f3fd054431e43cf17f6e6dee8a26`). Chỉ nhận định dạng MT5 có hậu tố `Z`; thời gian không có `Z`, lệch múi giờ hoặc sai định dạng vẫn bị loại. Phát lại 22 payload bị loại qua bộ kiểm tra đã sửa: 22/22 hợp lệ.
- **Gate chạy lại tại SHA mới:** 108/108 unit test, 27/27 replay/parity, 12/12 `test_phase3_1`, `BUNDLE_VALID`, smoke `m1-smoke-202610070642` = `SHADOW_READY`.
- **Run mới (2026-10-07):** V26 `P3-FWD-20261007T064249Z-44f045bf22b9` (authorization `p3-auth-1b3f5b8bcaadd282e28e681e`, bind offset 30627); V63 `P3-FWD-20261007T064300Z-44f045bf22b9` (authorization `p3-auth-223f76791148ef9db0d8546d`, bind offset 18097). Offset bind bằng kích thước file lúc dừng nên không có bản ghi mới nào xuất hiện trong lúc bảo trì. Cả hai `RUNNING`, `CONNECTED`, `campaign_id` đúng.
- **Chưa quyết (operator):** 22 bản ghi đã bị loại có được nạp lại và tính vào forward hay chỉ giữ làm bằng chứng. Tính đến hiện tại mọi mẫu forward thực sự bắt đầu từ run mới.
- **MT5-DATA:** terminal này tắt khoảng 21:43Z ngày 05/10 (không rõ lý do) nên ETHUSD/XAUUSD/EURUSD không có dữ liệu từ lúc đó (ba file vẫn 0 dòng, kể cả trước khi tắt). Mở lại 2026-10-07T06:32Z; Algo Trading được operator bật lúc 06:40Z.

## Cập nhật 2026-10-07: 22 bản ghi bị loại đã nạp lại, gắn nhãn LATE_NOT_FORWARD

- **Quyết định operator:** nạp lại nhưng tách khỏi forward (lựa chọn 1).
- **PR #11** (`feat: store timestamp-rejected observations as LATE_NOT_FORWARD evidence`) merge vào `main` (`da4732b5d88a1002fd44b59cd2de06fa37bbf6d5`): migration 011 (bảng `phase3_late_ingested_observations`, ràng buộc `forward_eligible = 0` và `ingest_class = 'LATE_NOT_FORWARD'`) và lệnh `late-ingest-rejected`.
- **Chạy trên DB máy 1** từ clone báo cáo (checkout runtime vẫn ở `44f045bf22b9f3fd054431e43cf17f6e6dee8a26`, tracked tree sạch, collector không phải khởi động lại). DB sao lưu bằng SQLite backup trước khi chạy (`evidence\pre-lateingest-20261007.sqlite`).
  - V26: 15 candidates, 15 stored, 0 still_invalid.
  - V63: 7 candidates, 7 stored, 0 still_invalid.
- **Kiểm tra sau khi chạy:** `integrity_check` ok; không có prediction mới từ 22 bản ghi này; các bản ghi hợp lệ của run mới (1 observation, 1 prediction mỗi hệ) không đổi. `counts_toward_forward=false`.
- **Lưu ý cho máy 2:** DB runtime của máy 1 đã ở migration 011 trong khi checkout runtime còn ở commit chưa có file migration này; code cũ chỉ áp migration còn thiếu nên không ảnh hưởng. Lần cập nhật checkout runtime kế tiếp (phải `prepare-forward` lại) sẽ đồng bộ.
- **Một sai sót quy trình:** trong khi viết PR #11, một số file được chỉnh nhầm trong checkout runtime trong vài phút trước khi chuyển sang clone báo cáo và khôi phục về `main` sạch. Không có lần khởi động lại collector nào xảy ra trong khoảng đó.
