# Máy 1 — Bàn giao kích hoạt thu dữ liệu forward Phase 3.1 (2026-10-01)

Tài liệu này dành cho **agent (Codex/Claude) chạy trên máy 1**. Đọc toàn bộ trước khi chạy lệnh nào.
Nếu một bước có điều kiện dừng bị kích hoạt: dừng, ghi lại bằng chứng và báo operator. Không tự sửa để
"cho qua".

## 1. Chỉ thị operator

```text
OPERATOR_ID=billy7d
DIRECTIVE_UTC_DATE=2026-10-01
DIRECTIVE_SOURCE=OPERATOR_CHAT_ON_MACHINE_2
SCOPE=PHASE3_1_FORWARD_SHADOW_COLLECTION_ON_MACHINE_1
PRIMARY_SYSTEM=V26 (MagicNumber 26072626, preset 83)
SECONDARY_SYSTEM=V63 (MagicNumber 26072663, preset 84) — collector V63 là bước tùy chọn, xem §8
```

Operator cho phép agent trên máy 1:

- clone/checkout repository tại commit bàn giao, chạy test, compile kiểm tra;
- tạo runtime root `E:\build-bot-runtime\phase3\` và cấu hình không chứa credential;
- compile EA trong terminal **demo** và chuẩn bị chart BTCUSD H1 với preset 83/84;
- sinh gate evidence, chạy `prepare-forward` để tạo authorization local, `start-forward`;
- cài và bật scheduled task `BuildBot-Phase3-Forward` cho collector;
- xuất báo cáo health/coverage và push trên **branch riêng** (§9).

Agent **không được**:

- nhập mật khẩu, investor password, 2FA hay bất kỳ credential nào. Operator tự đăng nhập;
- bật Algo Trading. Operator tự bật sau khi agent xác nhận tài khoản là demo (§5);
- gắn EA vào tài khoản không phải demo;
- sửa `outputs/Mentor_RSI_MTF_v1.mq5`, preset 79/80/83/84 hay bất kỳ input nào trên chart;
- động vào Gate B/A1: `C:\Program Files\MetaTrader 5`, `D:\Trading\MT5-GateB-Acceptance`, script
  `tools/gate_b_a1_cleanup_admin.ps1`, `scripts/phase3/execute_gate_b_a1.ps1`, Gate C Lite;
- xóa file, dừng tiến trình MT5 không do agent khởi động, chạy lệnh cần quyền admin;
- commit, pull hay checkout trong **checkout runtime** khi run đang chạy (§9);
- đưa outcome/chất lượng dự đoán vào báo cáo gửi máy 2 ngoài lịch (§9).

```text
LIVE_TRADING=NO
EXECUTION_AUTHORITY=NONE           (collector Phase 3)
EA_EXECUTION=DEMO_ONLY             (EA forward demo như runbook)
AUTO_MERGE=NO
```

## 2. Bối cảnh ngắn

- Collector chỉ đọc file JSONL mà EA ghi ra, chấm điểm bằng bundle đóng băng và chờ outcome. Nó không
  gửi lệnh.
- Preset forward cũ 79/80 có `ExportPhase3OpportunityJsonl=false` (mặc định), nên **không** sinh luồng
  opportunity. Preset mới:

| Preset | Nội dung | SHA-256 (byte-preserved, `-text`) |
|---|---|---|
| `outputs/presets/83_v26_forward_demo_p3obs.set` | 79 + `ExportPhase3OpportunityJsonl=true` + `ExportPhase3OpportunityInTester=true` | `b5ead1a5e54d3ca2f473c04d8c01c5cb9e2508e339b1793dc67f8f00d96b2abf` |
| `outputs/presets/84_v63_forward_demo_p3obs.set` | 80 + hai cờ trên | `07ecf4059efd8a05224e6e8536f2273aebc0fadecf16d22710ec69a7c665dfac` |

  Hai file này giống từng byte với preset candidate đã qua execution parity Phase 3.1
  (`reports/trading_agent/phase3_1/execution_parity_report.md`: chênh lệch signal/order/deal = 0 cho V26
  và V63). Cờ `InTester` không có tác dụng trên chart live.
- Source EA: git blob `49f924e3927d8cb3ee1ee4b7369fd8294b030c9f` (`git rev-parse HEAD:outputs/Mentor_RSI_MTF_v1.mq5`).
  Dùng blob hash thay vì SHA-256 file vì `core.autocrlf` có thể đổi line ending trong working tree.
- Bundle: `p3-bundle-577e5dfd0702c52c8f5318063703dd616a633704444ba5371e1c74e6dc080c6a`, cutoff
  `2023-12-30T08:00:00Z`.

## 3. File operator phải chép từ máy 2 sang máy 1

Hai artifact bị `.gitignore` theo chính sách repo (serialized model state), nên không có trong Git:

| File | SHA-256 | Đích trên máy 1 |
|---|---|---|
| `model_bundle.json` | `36bcdbeb69694f45ec46d83a2c946dbebf935db3f2046b1684cead9655606c31` | `E:\build-bot-runtime\phase3\assets\model_bundle.json` |
| `history_index.json` | `f84d36c48df3269f268b41f0c6102098ae17698dfe88cc643d17b8ae982257f8` | `E:\build-bot-runtime\phase3\assets\history_index.json` |

Nguồn trên máy 2: `E:\build-bot\outputs\machine1_transfer_20261001\` (có `SHA256SUMS.txt`).
`history_index.json` được dựng lại ngày 2026-10-01 bằng `build-history-index` và có
`rows_fingerprint=7e972c3ae246738aac964efdee7e04e5e5f09b65f03b5d7b19fa718e1fb91f03`, `row_count=1002`,
khớp với Phase 3.1.

**Dừng** nếu SHA-256 không khớp. Không tự dựng lại model.

Nếu máy 1 dùng ổ khác E:, đổi mọi đường dẫn `E:\build-bot-runtime` và `E:\build-bot` trong tài liệu này
cho nhất quán và ghi lại trong báo cáo.

## 4. Preflight repository (máy 1)

```powershell
# Checkout runtime: chỉ dùng cho collector, không commit ở đây.
git clone https://github.com/billy7d/build-bot.git E:\build-bot     # nếu chưa có
cd E:\build-bot
git fetch origin
git checkout main
git pull --ff-only
git status --short --branch          # tracked tree phải sạch
git log -1 --format=%H               # ghi lại: đây là AUTHORIZED_SHA dự kiến
git rev-parse HEAD:outputs/Mentor_RSI_MTF_v1.mq5   # phải = 49f924e3927d8cb3ee1ee4b7369fd8294b030c9f
Get-FileHash outputs\presets\83_v26_forward_demo_p3obs.set -Algorithm SHA256
Get-FileHash outputs\presets\84_v63_forward_demo_p3obs.set -Algorithm SHA256

py -3 --version                      # cần 3.11+
py -3 -m compileall -q agent
py -3 -m unittest discover -s agent/tests
py -3 -m agent.phase3 validate-bundle
```

Điều kiện tiếp tục: tracked tree sạch; blob và hai SHA preset khớp §2; compileall PASS; toàn bộ unit test
PASS (máy 2 ghi 95/95 ở Python 3.11.9); `validate-bundle` trả `BUNDLE_VALID` với bundle id ở §2.

Ghi đường dẫn tuyệt đối của Python (`py -3 -c "import sys; print(sys.executable)"`) để đưa vào config.

## 5. Terminal MT5 demo

Theo `outputs/forward_demo_runbook.md` và `outputs/windows_laptop_stage1_setup.txt`: V26 và V63 chạy trên
**hai terminal, hai tài khoản demo, hai data-folder riêng** (thường là `C:\Trading\MT5-V26` và
`C:\Trading\MT5-V63`, hoặc `D:\Trading\MT5-V26` theo evidence Gate B). Agent liệt kê và báo operator
đường dẫn thực tế trước khi làm tiếp.

1. Chép `outputs/Mentor_RSI_MTF_v1.mq5` vào `MQL5\Experts\` của từng terminal. Compile bằng MetaEditor
   của chính terminal đó. Yêu cầu `0 errors, 0 warnings`. Ghi SHA-256 file `.ex5`.
2. Chép preset 83 vào `MQL5\Presets\` của terminal V26 và preset 84 vào terminal V63. Kiểm tra lại SHA-256.
3. **Operator** đăng nhập tài khoản demo trên từng terminal.
4. Agent xác nhận tài khoản là demo trước khi operator bật Algo Trading. Ví dụ: Journal/Experts log khi
   EA khởi tạo, dòng `INIT` trong `Mentor_RSI_MTF_forward.csv` hoặc tiêu đề cửa sổ terminal có "Demo".
   Không ghi số tài khoản, tên server hay IP vào bất kỳ file nào trong repo.
   **Dừng** nếu không chứng minh được tài khoản là demo.
5. Archive (di chuyển, không xóa) CSV forward cũ trong `MQL5\Files` của đúng terminal sang thư mục
   `archive-<ngày>` cạnh đó, theo runbook §4. Không động vào terminal còn lại.
6. Gắn EA vào chart **BTCUSD H1** (đúng tên symbol của broker), nạp preset 83 (V26) / 84 (V63). Đối chiếu
   các input bắt buộc của runbook §1.4 cùng `ExportPhase3OpportunityJsonl=true`.
7. **Operator** bật Algo Trading.
8. Agent kiểm tra:
   - Journal có `FORWARD telemetry initialized` và log mở file opportunity (đường dẫn in ra từ
     `TERMINAL_COMMONDATA_PATH`).
   - File tồn tại:

```text
%APPDATA%\MetaQuotes\Terminal\Common\Files\phase3\opportunities\Mentor_RSI_MTF_26072626_<Symbol>_H1.jsonl
%APPDATA%\MetaQuotes\Terminal\Common\Files\phase3\Mentor_RSI_MTF_26072626_<Symbol>_H1.jsonl   (legacy diagnostic)
```

   - Với terminal portable (`/portable`), Common folder vẫn là của user Windows. Xác nhận đường dẫn
     thật từ log, không giả định.

Observer chỉ ghi khi có shadow signal V81 tại nến H1 đã đóng. Có thể phải chờ **vài giờ đến hơn một
ngày** mới có dòng đầu tiên. `prepare-forward` yêu cầu file có ít nhất một bản ghi
`phase3-opportunity-observation/1` hợp lệ. Trong lúc chờ, làm tiếp §6–§7 rồi quay lại.

## 6. Runtime root và config

```powershell
$root = 'E:\build-bot-runtime\phase3'
'config','assets','db','logs','state','control','evidence' | ForEach-Object { New-Item -ItemType Directory -Force -Path (Join-Path $root $_) | Out-Null }
# Chép 2 artifact ở §3 vào $root\assets rồi kiểm tra SHA-256.
```

`E:\build-bot-runtime\phase3\config\forward.json` (thay `<Symbol>` và `<PYTHON_EXE>` bằng giá trị thật;
dùng `\\` trong JSON):

```json
{
  "schema": "phase3-forward-runtime/1",
  "runtime_root": "E:\\build-bot-runtime\\phase3",
  "repo_path": "E:\\build-bot",
  "python_path": "<PYTHON_EXE>",
  "bundle_manifest": "E:\\build-bot\\reports\\trading_agent\\phase3\\shadow_bundle_manifest.json",
  "model_bundle_path": "E:\\build-bot-runtime\\phase3\\assets\\model_bundle.json",
  "history_index_path": "E:\\build-bot-runtime\\phase3\\assets\\history_index.json",
  "telemetry_path": "C:\\Users\\<user>\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files\\phase3\\Mentor_RSI_MTF_26072626_<Symbol>_H1.jsonl",
  "primary_opportunity_path": "C:\\Users\\<user>\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files\\phase3\\opportunities\\Mentor_RSI_MTF_26072626_<Symbol>_H1.jsonl",
  "runtime_db": "E:\\build-bot-runtime\\phase3\\db\\phase3-forward.sqlite",
  "telemetry_format": "jsonl",
  "execution_mode": "NONE",
  "live_execution_enabled": false,
  "heartbeat_interval_seconds": 30,
  "heartbeat_stale_seconds": 120,
  "poll_interval_seconds": 5.0,
  "task_name": "BuildBot-Phase3-Forward"
}
```

Kiểm tra config load được (không cần file telemetry tồn tại ở bước này):

```powershell
py -3 -c "from agent.phase3.forward import load_forward_config as L; c=L(r'E:\build-bot-runtime\phase3\config\forward.json'); print(c.to_dict()['execution_mode'], c.primary_opportunity)"
```

## 7. Gate evidence

`prepare-forward --gates` cần một JSON với bốn trạng thái `PASS`. Mỗi trạng thái phải đến từ lệnh chạy
**trên máy 1, tại AUTHORIZED_SHA, trong phiên này**. Không chép trạng thái từ report cũ.

| Gate | Nguồn bằng chứng |
|---|---|
| `replay_parity_status` | `py -3 -m unittest agent.tests.test_phase3 agent.tests.test_phase3_canonical` PASS (contract replay/parity) |
| `smoke_status` | `py -3 -m unittest agent.tests.test_phase3_1` PASS, kèm `start-shadow` smoke với DB tạm (lệnh dưới) |
| `db_integrity_status` | `prepare-forward` tự kiểm tra `integrity_check` và `foreign_key_check` của runtime DB. Ghi `PASS` sau khi xác nhận DB mở được ở bước smoke |
| `one_way_safety_status` | `execution_api_path_count == 0` (prepare-forward tự quét lại) và config `execution_mode=NONE` |

```powershell
py -3 -m agent.phase3 start-shadow --run-id m1-smoke-<yyyyMMddHHmm> --db E:\build-bot-runtime\phase3\evidence\smoke.sqlite --report-dir E:\build-bot-runtime\phase3\evidence\smoke-report --model-bundle E:\build-bot-runtime\phase3\assets\model_bundle.json --history-json E:\build-bot-runtime\phase3\assets\history_index.json
```

Ghi `E:\build-bot-runtime\phase3\evidence\gates.json`:

```json
{
  "schema": "machine1-forward-gates/1",
  "authorized_sha": "<AUTHORIZED_SHA>",
  "generated_at_utc": "<UTC>",
  "replay_parity_status": "PASS",
  "smoke_status": "PASS",
  "db_integrity_status": "PASS",
  "one_way_safety_status": "PASS",
  "execution_api_path_count": 0,
  "evidence": {
    "unit_tests": "<số test PASS/tổng>",
    "smoke_run_id": "m1-smoke-...",
    "python": "<phiên bản>"
  }
}
```

Nếu bất kỳ lệnh nào FAIL thì không ghi `PASS`. Dừng và báo.

## 8. Authorization và khởi động collector

Chỉ làm sau khi file opportunity V26 có ít nhất một bản ghi hợp lệ.

```powershell
cd E:\build-bot
py -3 -m agent.phase3 prepare-forward --runtime-config E:\build-bot-runtime\phase3\config\forward.json --gates E:\build-bot-runtime\phase3\evidence\gates.json
# → ghi E:\build-bot-runtime\phase3\config\forward_authorization.json

# Kiểm tra ngắn ở foreground, sau đó để task resume cùng run.
py -3 -m agent.phase3 start-forward --runtime-config E:\build-bot-runtime\phase3\config\forward.json --max-iterations 3
py -3 -m agent.phase3 status-runtime --runtime-config E:\build-bot-runtime\phase3\config\forward.json --json

.\scripts\phase3\install_forward_task.ps1 -RuntimeConfig E:\build-bot-runtime\phase3\config\forward.json -Start
.\scripts\phase3\status_forward_task.ps1
py -3 -m agent.phase3 status-runtime --runtime-config E:\build-bot-runtime\phase3\config\forward.json --json
```

Kỳ vọng sau vài phút:

```text
FORWARD_COLLECTION_STATUS=ACTIVE
persistent_runtime_status=RUNNING
telemetry_status=CONNECTED
heartbeat age < heartbeat_stale_seconds (120)
execution_mode=NONE, live_execution_enabled=false
```

Lưu ý:

- Collector **bind tại cuối file** ở lần quan sát đầu. Bản ghi có trước thời điểm start không được tính
  là forward sample. Đây là hành vi đúng.
- Task chạy khi user đăng nhập (`AtLogOn`, `InteractiveToken`). Máy 1 phải giữ phiên đăng nhập, tắt sleep
  và đặt MT5 tự khởi động theo `windows_laptop_stage1_setup.txt`. Việc thay đổi cài đặt nguồn/sleep do
  operator làm.
- `FORWARD_SAMPLE_COUNT` chỉ tăng khi opportunity mới được ghi **và** outcome đã resolve (sau tối đa 48
  nến H1). Số mẫu dự kiến chỉ khoảng 1–2 mỗi ngày.

**V63 (tùy chọn, cần operator xác nhận riêng):** collector thứ hai dùng runtime root
`E:\build-bot-runtime\phase3-v63\`, config riêng trỏ `..._26072663_<Symbol>_H1.jsonl`, DB riêng,
`task_name` riêng (`BuildBot-Phase3-Forward-V63`), authorization riêng. Không dùng chung DB hay lock
với V26.

## 9. Báo cáo về máy 2

**Không commit trong `E:\build-bot`.** Authorization ràng buộc HEAD và tracked tree sạch; commit, pull
hay checkout ở đó sẽ làm collector fail closed khi resume.

Dùng một clone riêng cho báo cáo:

```powershell
git clone https://github.com/billy7d/build-bot.git E:\build-bot-reports
cd E:\build-bot-reports
git checkout -b ops/machine1-forward-activation-20261001
```

Ghi `reports/trading_agent/phase3_forward_node_ops/machine1_forward_activation_20261001.md` gồm:

- AUTHORIZED_SHA, authorization_id, run_id, thời điểm start (UTC);
- blob source EA, SHA-256 preset, SHA-256 `.ex5`, SHA-256 hai artifact §3;
- kết quả §4 và §7 (số test, trạng thái gate);
- output `status-runtime --json` sau khi đã **xóa** đường dẫn có tên user, số tài khoản, server và IP;
- task state;
- mọi sai lệch so với tài liệu này và lý do.

**Không đưa vào:** outcome, hit rate, Brier/AUC, nội dung JSONL, CSV giao dịch, account/server/IP,
credential. Theo `docs/trading_agent/PHASE4_ACCELERATED_LEARNING_DESIGN.md` §6.4, dữ liệu forward là holdout
của BTCUSD H1. Metric dự đoán chỉ được mở theo lịch đánh giá cố định.

Commit và push branch đó. Không merge vào `main` (operator review trên máy 2).

Báo cáo health định kỳ (khi operator yêu cầu) dùng cùng định dạng: heartbeat, số opportunity đã ingest,
độ trễ, lỗi, uptime.

## 10. Điều kiện dừng

Dừng ngay, giữ nguyên toàn bộ file/log và báo operator khi:

- SHA/blob/bundle không khớp; test hoặc gate FAIL;
- không chứng minh được tài khoản là demo;
- Journal có `initialization failed`, lỗi mở file opportunity, hoặc EA bị gỡ khỏi chart;
- `status-runtime` báo `FAILED`, `telemetry_status` không về `CONNECTED` sau 2 nến H1 có tín hiệu,
  hoặc heartbeat stale lặp lại;
- collector báo truncation cùng identity (fail closed);
- DD tài khoản demo chạm 8%, có `ACTUAL_RISK_VIOLATION`, `POST_FILL_VIOLATION`, `STOP_MODIFY_FAIL` hoặc
  `MISSING_STATE` (runbook forward).

Dừng collector (không ảnh hưởng MT5):

```powershell
.\scripts\phase3\stop_forward_task.ps1
py -3 -m agent.phase3 stop-forward --runtime-config E:\build-bot-runtime\phase3\config\forward.json --run-id <run_id>
```

## 11. Prompt gợi ý cho agent trên máy 1

```text
Bạn đang ở máy 1 (MT5 demo + collector) của repo build-bot. Đọc
docs/trading_agent/phase3/MACHINE1_FORWARD_COLLECTION_HANDOFF_20261001.md, README.md,
outputs/forward_demo_runbook.md và agent/phase3/README.md. Thực hiện tuần tự §3–§9 của tài liệu
bàn giao. Dừng và hỏi operator ở mỗi bước cần operator: chép artifact, đăng nhập demo, bật Algo
Trading, xác nhận đường dẫn terminal, và bật collector V63. Không nhập credential, không sửa
EA/preset, không động vào Gate B/A1, không commit trong checkout runtime. Kết thúc bằng báo cáo §9
trên branch riêng.
```
