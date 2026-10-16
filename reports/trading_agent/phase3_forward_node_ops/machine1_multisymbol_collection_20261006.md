# Machine 1 — Thu dữ liệu forward ETHUSD, XAUUSD, EURUSD H1 (báo cáo ban đầu, 2026-10-06)

Theo `docs/trading_agent/phase3/MACHINE1_MULTISYMBOL_COLLECTION_20261006.md`. Báo cáo không có nội dung JSONL, outcome, PnL, số tài khoản hay server.

## Môi trường

- Terminal thứ ba: `D:\Trading\MT5-DATA`, chạy chế độ portable, data folder riêng trong thư mục đó. Tạo bằng cách copy chương trình (`terminal64.exe`, `MetaEditor64.exe`, `metatester64.exe`, `Sounds`) từ bản V26, SHA-256 `terminal64.exe` và `MetaEditor64.exe` khớp V26. Không copy cấu hình, dữ liệu hay tài khoản; chỉ chép `servers.dat` (danh sách server broker) từ V26 để đăng nhập được broker.
- Tài khoản demo thứ ba, kiểu **Hedge**, do operator đăng nhập (agent không nhập mật khẩu). Xác nhận demo bằng tiêu đề cửa sổ và Journal (`demo account - hedging mode`); số tài khoản khác V26 và V63.
- Repo: `D:\Trading\buildbot` ở `258b550384ebed08c6e0516b951a55d38d6a906f`.

## Symbol thật của broker

| Mã | Symbol broker | Ghi chú |
|---|---|---|
| ETH | `ETHUSD` | không hậu tố |
| XAU | `XAUUSD` | broker còn có `XAUUSD247`, **không dùng** |
| EUR | `EURUSD` | không hậu tố |

Không có mã nào bị bỏ.

## Hash

| Mục | SHA-256 |
|---|---|
| Blob source EA | `49f924e3927d8cb3ee1ee4b7369fd8294b030c9f` (khớp) |
| Preset 85 (ETHUSD, magic 26072701) | `21ae002537bf61b76bfc81f336d8ae1c07527827f796b1445ebd57bbf837d120` (khớp) |
| Preset 86 (XAUUSD, magic 26072702) | `31ecff1b79ad05b3da9ac53840b71701ec34679e9d8f525197b9293b51d363aa` (khớp) |
| Preset 87 (EURUSD, magic 26072703) | `34acce60621a2bc7cf72c11fca8c1bb40a7a4db882013fa268c88439a4d8a229` (khớp) |
| `.ex5` (compile bằng MetaEditor của MT5-DATA, 0 errors, 0 warnings) | `8bc81e8b8a761e3cf0043d2703e47292ed7cea83ebd0fb576f6ec6f182e879b6` |

## Gắn EA

- EA được gắn lên ba chart H1 lúc **2026-10-05T17:59:29Z**. Journal xác nhận từng EA khởi tạo, và mỗi cái mở đúng `Mentor_RSI_MTF_<magic>_<symbol>_H1.jsonl` (telemetry và opportunity) theo bảng trên. Đối chiếu Inputs: preset nạp 93 input, `MagicNumber` đúng, `ExportPhase3OpportunityJsonl=true`.
- Algo Trading được operator bật lúc **2026-10-05T18:02:42Z**. Operator bật/tắt lại lúc 18:04. Chưa có lệnh hay lỗi risk nào trong Journal tại thời điểm báo cáo.
- Contract spec (không có tài khoản/server): `D:\Trading\build-bot-runtime\phase4-data\contract_specs_20261006.json`. `tick_value` đo lúc chưa có tick nên bằng 0, và **thiếu giờ giao dịch**; cần bổ sung.

## Sai lệch so với tài liệu

1. **Cách gắn EA:** không có công cụ điều khiển giao diện MT5, nên chart và EA được gắn bằng hai script do agent viết đặt trong `MT5-DATA\MQL5\Scripts` (`ExportContractSpecs`, `ApplyDataCharts`) và ba template `mentor_{eth,xau,eur}.tpl` dựng từ nội dung preset 85/86/87 (không sửa preset). Terminal phải khởi động bằng `terminal64.exe /portable /config:start_apply.ini` để dựng lại đúng ba chart (script đóng các chart khác trước để không có EA trùng magic).
2. **Sự cố thử nghiệm:** khoảng 00:56–00:59 giờ máy ngày 06/10 (17:56–17:59Z), ETH và XAU có lúc chạy hai bản EA trùng magic do chart thừa trong profile. Các file opportunity đều 0 byte nên không có bản ghi trùng.
3. **`MT5-DATA` chưa tự khởi động và task snapshot chưa cài:** chờ operator đồng ý (bước 12–13 của tài liệu).
4. **Min lot ETHUSD là 0.1**, cao hơn EA dùng cho BTCUSD, nên lệnh ETH sẽ bị làm tròn lên mức tối thiểu.

## Còn thiếu (cập nhật sau)

- Trạng thái task snapshot hằng ngày và số dòng mỗi file sau 24 giờ.
- Giờ giao dịch từng mã và `tick_value`.

## Cập nhật 2026-10-06: contract spec v2 (tick value và giờ giao dịch)

Đọc bằng script trong terminal MT5-DATA lúc 2026-10-05T18:13:45Z, lưu ở `D:\Trading\build-bot-runtime\phase4-data\contract_specs_20261006_v2.json` (schema `machine1-contract-specs/2`). Không có tài khoản hay server.

| Mã | contract size | digits | point | tick size | tick value | min lot | step | spread hiện tại (points) |
|---|---|---|---|---|---|---|---|---|
| ETHUSD | 1 | 2 | 0.01 | 0.01 | 0.01 | 0.1 | 0.01 | 70 |
| XAUUSD | 100 | 3 | 0.001 | 0.001 | 0.1 | 0.01 | 0.01 | 168 |
| EURUSD | 100000 | 5 | 0.00001 | 0.00001 | 1.0 | 0.01 | 0.01 | 6 |

Giờ giao dịch theo giờ server của broker (server trừ UTC = 0 giây tại thời điểm đo):

- **ETHUSD:** 24/7 (00:00-00:00 mọi ngày).
- **XAUUSD:** CN 22:01-24:00; T2–T5 00:00-20:58 và 22:00-24:00; T6 00:00-20:58; T7 nghỉ.
- **EURUSD:** CN 21:05-24:00; T2–T5 24h; T6 00:00-20:59; T7 nghỉ.

Lưu ý: spread XAUUSD lúc đo (168 points) cao vì ngoài giờ thanh khoản; không dùng làm đại diện. Sau khi đọc spec, MT5-DATA được khởi động lại một lần (bình thường).

## Task đã cài (operator đồng ý 2026-10-05)

- `BuildBot-Phase4-DataSnapshot`: hằng ngày 00:30 giờ máy, chạy thử thành công; snapshot đầu có 3 file 0 dòng.
- `BuildBot-MT5-DATA-Autostart`, `BuildBot-MT5-V26-Autostart`, `BuildBot-MT5-V63-Autostart`: mở terminal khi đăng nhập Windows (chờ 30s/30s/45s). Chưa thử; lần khởi động lại máy đầu tiên là lần thử thật.

## Cập nhật 2026-10-08: sau 24 giờ chạy liên tục của MT5-DATA

Số liệu lúc 2026-10-08T16:17Z. MT5-DATA chạy liên tục từ 2026-10-07T15:15Z (mở bằng scheduled task); Algo Trading do operator bật 15:20Z. Không đưa vào báo cáo nội dung JSONL, outcome hay PnL.

| File (magic) | Số dòng opportunity | Ghi chú |
|---|---|---|
| `...26072701_ETHUSD_H1.jsonl` | 1 | bản ghi duy nhất xuất hiện 2026-10-07 07:00Z, trước lần mở lại |
| `...26072702_XAUUSD_H1.jsonl` | 0 | |
| `...26072703_EURUSD_H1.jsonl` | 0 | |

- Trong 25 giờ chạy liên tục không có dòng nào mới ở ba file. Điều kiện dừng "0 dòng sau 72 giờ khi thị trường mở" **chưa đủ** vì MT5-DATA bị tắt từ 2026-10-05T21:43Z đến 2026-10-07T15:15Z; thời gian EA thực sự chạy cho XAUUSD/EURUSD tới nay khoảng 1,5 ngày. Đây vẫn chưa là kết luận về tần suất tín hiệu của chiến lược trên các mã này.
- Snapshot hằng ngày: đã chạy các ngày 2026-10-06 (17:30Z) và 2026-10-07 (17:30Z); manifest ghi đủ ba file mỗi lần (ETH 1 dòng, XAU/EUR 0 dòng).
- MT5-DATA từng tắt hai lần (21:43Z ngày 05/10; 07:00Z ngày 07/10). Lần thứ hai có lệnh demo ETHUSD mở lúc 07:00Z (bán 0.3, rủi ro 0,5%) trước khi terminal tắt, nằm không có EA quản lý khoảng 8 giờ đến lúc mở lại. Nghi terminal bị tắt theo phiên làm việc của agent vì được mở từ phiên đó; từ 2026-10-07T15:15Z được mở bằng task nên chạy độc lập, chạy liên tục sau đó.

## Cập nhật 2026-10-14: XAUUSD/EURUSD kẹt MISSING_STATE cả tuần (lỗi EA khi khởi tạo)

- **Triệu chứng:** sau hơn 100 giờ thị trường mở, `XAUUSD` và `EURUSD` vẫn 0 dòng opportunity (ETHUSD 5 dòng). Log EA của hai mã không có dòng `DIAG` nào từ 2026-10-07T15:16Z.
- **Bằng chứng (DIAG_SUMMARY lúc OnDeinit, 2026-10-14T11:09Z, cho run từ 2026-10-07T15:20Z):**
  - ETHUSD: `missingStateBars=0`, shadow `buildFail=0`.
  - XAUUSD: `missingStateBars=111`, shadow `events=1`, `buildFail=111`.
  - EURUSD: `missingStateBars=116`, shadow `buildFail=116`.
  Tức là mọi nến H1 của hai mã đều thất bại ở `BuildState` (cần 260 giá trị RSI/ATR/giá cho D1/H4/H1/M15) và bị bỏ qua.
- **Lịch sử không thiếu:** script chỉ đọc `DiagBars` (2026-10-14T10:52Z) cho thấy cả ba mã đủ ≥260 nến và `CopyBuffer` RSI/ATR trả đủ 260 ở cả bốn khung, `SERIES_SYNCHRONIZED=1`.
- **Kết luận (suy luận):** chỉ báo do EA tạo lúc khởi tạo ngay sau khi terminal mở (2026-10-07T15:15Z) bị kẹt ở hai chart này và không tự phục hồi. Khởi tạo lại EA lúc 2026-10-14T11:10Z thì cả hai dựng được trạng thái và in `DIAG` ngay ở nến 11:00Z.
- **Rủi ro:** lỗi có thể lặp lại ở bất kỳ lần khởi động lại terminal nào (kể cả V26/V63) và không có cảnh báo. Đề xuất cho người phụ trách EA: tạo lại handle chỉ báo hoặc báo lỗi rõ khi `BuildState` thất bại liên tiếp; agent trên máy 1 không sửa EA.
- **Sai lệch:** XAUUSD/EURUSD đang chạy với `DiagnosticsEveryBars=1` (preset gốc là 24) để theo dõi EA còn xử lý nến hay không; chỉ ảnh hưởng tần suất in log, các input chiến lược và magic giữ nguyên. Áp bằng template `mentor_{xau,eur}_diag1.tpl` qua script `ApplyDataChartsDiag` và task `BuildBot-MT5-DATA-DiagRun` (operator đồng ý).
- **Dữ liệu bị mất:** XAUUSD và EURUSD không có dữ liệu opportunity hợp lệ từ 2026-10-05 đến 2026-10-14T11:00Z.

## Cập nhật 2026-10-16: parity bản sửa EA tự phục hồi handle (`fix/ea-core-handle-recovery`)

Theo `docs/trading_agent/phase3/EA_CORE_HANDLE_RECOVERY_20261016.md` §5. Kết quả: **PARITY PASS** cho cửa sổ bắt buộc 2023.04.01–2023.12.31, cả V26 và V63. Chưa triển khai EA mới lên chart nào.

- **Môi trường:** terminal V26 (`D:\Trading\MT5-V26`) đang chạy live nên không chạy tester trong chính nó (tester bằng dòng lệnh cần tắt terminal). Dùng bản sao portable cô lập `D:\Trading\parity-v26-coreh-20261016`: cùng binary build 6230, cùng tài khoản demo `Exness-MT5Trial6` (log: `authorized ... demo account`), không chart, `[Experts] Enabled=0`, `AllowLiveTrading=0`. V26/V63/MT5-DATA và collector không bị dừng hay đụng tới.
- **Source:** baseline `main` `307842fcb2cadee9416a1f0245a3d395b4500a79`; candidate `8aef15c` (`fix(ea): recover stuck core indicator handles ...`). Compile bằng MetaEditor của V26 (build 6230):

  | Bản | File | Kết quả | Kích thước | SHA-256 `.ex5` |
  |---|---|---|---:|---|
  | Baseline | `ParityBaseline.ex5` | 0 errors, 0 warnings | 300472 | `2607022911B28E2A7029E1F6D3877E468AB44EB31163791C4BFE070A2C75F569` |
  | Candidate | `ParityCandidate.ex5` | 0 errors, 0 warnings | 305076 | `50FDDBF76A9B6CD9FB662C0174B100B44ABA28B8846A01D377A1F198CBB92477` |

- **Cấu hình tester:** BTCUSD H1, `Model=4`, deposit 5000 USD, leverage 1:10, `ExecutionMode=0`. Preset `83_v26_forward_demo_p3obs.set` và `84_v63_forward_demo_p3obs.set` từ `main`, **chỉ đổi** `ExportPhase3OpportunityInTester=true` thành `false` (giống nhau cho baseline và candidate) để tester không ghi vào file JSONL live; exporter này chỉ quan sát, không ảnh hưởng lệnh. Lý do: xem sự cố 2026-10-16 trong `machine1_forward_activation_20261001.md`.
- **Sai lệch dữ liệu:** server demo chỉ có real ticks từ 2026-01-01, nên cửa sổ 2023 chạy bằng tick sinh từ M1 (`no real ticks, every tick generation used`). Parity vẫn hợp lệ vì baseline và candidate cùng môi trường, cùng 31.307.982 tick, 6576 nến.
- **So sánh** bằng `tools/mt5/compare_execution_regression.py --require-diagnostics` (journal candidate đã bỏ dòng `CORE_HANDLE_*` và 3 bộ đếm mới) và diff toàn bộ journal theo từng dòng (bỏ tiền tố thời gian thực, tên file expert, dòng input `CoreHandleRecoveryBars=3`, thời gian đồng bộ). Net, PF, DD được so khớp nhưng không ghi giá trị (kết quả niêm phong).

  | Preset, cửa sổ | Lệnh (B/C) | Deal (B/C) | Cycle (B/C) | Signal mở lệnh | OrderSend | Net/PF/DD | Diagnostics | Diff journal | `CORE_HANDLE_*` |
  |---|---:|---:|---:|---:|---:|---|---|---:|---:|
  | V26, 2023.04.01–12.31 | 148 / 148 | 246 / 246 | 93 / 93 | 93 / 93 | 385 / 385 | giống hệt | equal | 0 | 0 |
  | V63, 2023.04.01–12.31 | 142 / 142 | 232 / 232 | 86 / 86 | 86 / 86 | 356 / 356 | giống hệt | equal | 0 | 0 |

  `DIAG_SUMMARY forward` của candidate: `coreHandleStaleChecks=0 coreHandleRecreated=0 coreHandleRecreateFailed=0` (đúng kỳ vọng: handle khỏe trong tester).
- **Report:** `D:\Trading\parity-v26-coreh-20261016\reports\parity\{v26,v63}_{base,cand}_2023.htm`; SHA-256: v26 base `0082E751...8712`, v26 cand `4EC7A0EC...54F7`, v63 base `CBA92619...3500`, v63 cand `8A9797F4...FFDD` (khác nhau chỉ do tên expert và thời gian chạy). Journal tách riêng ở `journals\`. Không commit report thô.
- **Cửa sổ thêm 2025.01.01–2026.07.01: PASS** (cùng cấu hình, cùng cách so sánh):

  | Preset | Lệnh (B/C) | Deal (B/C) | Cycle (B/C) | Signal mở lệnh | OrderSend | Net/PF/DD | Diagnostics | Diff journal | `CORE_HANDLE_*` |
  |---|---:|---:|---:|---:|---:|---|---|---:|---:|
  | V26 | 330 / 330 | 602 / 602 | 269 / 269 | 269 / 269 | 969 / 969 | giống hệt | equal | 0 | 0 |
  | V63 | 278 / 278 | 498 / 498 | 217 / 217 | 217 / 217 | 844 / 844 | giống hệt | equal | 0 | 0 |

  Report: `reports\parity\{v26,v63}_{base,cand}_2025_2026.htm`. Bộ đếm `coreHandle*` của candidate đều 0. Từ 2026.01.01 tester dùng real ticks, nên cửa sổ này phủ cả đoạn real ticks.
- **Kết luận:** đủ điều kiện §5 để đề xuất merge `fix/ea-core-handle-recovery`. Giới hạn: tester chỉ chứng minh không đổi hành vi khi handle khỏe; đường phục hồi (`CORE_HANDLE_RECREATED`) chưa được kích hoạt trong tester, sẽ chỉ kiểm chứng được khi triển khai thật trên MT5-DATA (§6). Triển khai và gắn chart vẫn chờ operator duyệt.
- File JSONL live của V26 giữ nguyên 87834 byte sau toàn bộ 8 lần chạy (đã kiểm tra lại).

## Cập nhật 2026-10-17: triển khai bản sửa core-handle lên MT5-DATA (VIỆC A, chưa xong)

Theo `docs/trading_agent/phase3/EA_CORE_HANDLE_RECOVERY_20261016.md` §6 bước 1–2, operator duyệt 2026-10-17. V26/V63 **không** cập nhật. Checkout runtime `D:\Trading\buildbot` không đổi.

- **Source:** `main` `5ec8c85d2e7b6e62b14509b2edb9c3ec46464dd0` lấy từ clone báo cáo; blob `outputs/Mentor_RSI_MTF_v1.mq5` = `d0a8ae26c2f21c482719ae5c9db7492df1e115f3` (khớp).
- **Sao lưu bản cũ:** `D:\Trading\MT5-DATA\llm-agent\backup_ea_20261016\` (`.mq5` blob `49f924e3…`, `.ex5`).
- **Compile** bằng MetaEditor của MT5-DATA (build 6230), compile thử trong thư mục tạm (đã xoá), rồi compile tại chỗ trong `MQL5\Experts` lúc **2026-10-16T17:01:37Z**:

  | Bản | Kết quả | Kích thước | SHA-256 `.ex5` |
  |---|---|---:|---|
  | Cũ (đang chạy từ 2026-10-05) | — | 300602 | `8bc81e8b8a761e3cf0043d2703e47292ed7cea83ebd0fb576f6ec6f182e879b6` |
  | Mới (`5ec8c85`) | 0 errors, 0 warnings | 305290 | `85AB9E065F7A37159D9D10D455AD2CAB3BCCDB2578CEF4A3CBEBE6C4FCB9BD72` |

- **Chưa gắn lại được:** compile bằng dòng lệnh không làm terminal nạp lại EA (journal terminal và log EA không có dòng `removed`/`loaded successfully` sau 17:01Z). Ba chart vẫn chạy **code cũ trong bộ nhớ**; file `.ex5` trên đĩa đã là bản mới, nên lần khởi động terminal kế tiếp (task `BuildBot-MT5-DATA-DiagRun`/`-Autostart`) sẽ nạp bản mới.
- **Cần operator:** gắn lại bằng cách khởi động lại MT5-DATA (task DiagRun dựng lại 3 chart, giữ template `diag1` cho XAU/EUR). Các lần khởi động trước (07/10, 14/10) đều phải bật Algo Trading bằng tay, nên đang chờ operator. Mốc "thời điểm đổi build" chính thức là lúc EA mới được nạp trên chart, sẽ ghi sau.
- **Còn phải kiểm sau khi nạp:** journal EA khởi tạo, mở đúng `phase3/opportunities/Mentor_RSI_MTF_<magic>_<symbol>_H1.jsonl`, không có `MISSING_STATE` kéo dài ở nến H1 kế tiếp; theo dõi `CORE_HANDLE_*` sau mỗi lần terminal khởi động lại.

## Cập nhật 2026-10-17: kiểm chứng tách file opportunity khi chạy tester (VIỆC B) — PASS

Theo `docs/trading_agent/phase3/EA_TESTER_TELEMETRY_ISOLATION_20261017.md` §3, branch `fix/ea-tester-telemetry-isolation` (`2fcfc270cc403982947d3d9fd381534b7fa7bdf9`, blob `9ae350e8…`). Không merge.

- **Môi trường:** bản sao cô lập `D:\Trading\parity-v26-coreh-20261016` (tài khoản demo, không chart, `[Experts] Enabled=0`, `AllowLiveTrading=0`). V26/V63/MT5-DATA không bị dừng hay đụng tới.
- **Compile** (MetaEditor của bản sao, build 6230):

  | Bản | Source | Kết quả | Kích thước | SHA-256 `.ex5` |
  |---|---|---|---:|---|
  | `TelemBaseline` | `main` `5ec8c85` | 0 errors, 0 warnings | 304868 | `A25690CD15B12936690034D6346236F129C74EFDECD8A3E5A314F6A1173FC31A` |
  | `TelemCandidate` | `2fcfc27` | 0 errors, 0 warnings | 305648 | `8BFC9AD103F9A73499ED915C14ACCBB68F250D2303B1580251D94D2AB53C28ED` |

- **Cấu hình:** BTCUSD H1, `Model=4`, 2023.04.01–2023.12.31, deposit 5000, 1:10. Baseline dùng `83_v26_forward_demo_p3obs_parity.set` (chỉ khác preset 83 ở `ExportPhase3OpportunityInTester=false`); candidate dùng preset 83 nguyên bản (SHA-256 `b5ead1a5…2abf`, cờ `true`), chạy hai lần. Chạy 18:02Z–18:11Z.
- **File live** `Common\Files\phase3\opportunities\` (đọc bằng `FileShare.ReadWrite`, chỉ đọc), đo trước (18:02:18Z), giám sát mỗi 15 giây đến 18:33Z, và đo lại 20:17Z: **cả 6 file không đổi kích thước và SHA-256**.

  | File | Byte | SHA-256 |
  |---|---:|---|
  | `..._26062901_BTCUSD_M15.jsonl` | 0 | `E3B0C442…B855` |
  | `..._26072626_BTCUSD_H1.jsonl` (V26) | 87834 | `589CB591…4397` |
  | `..._26072663_BTCUSD_H1.jsonl` (V63) | 41848 | `CA948028…0E4D` |
  | `..._26072701_ETHUSD_H1.jsonl` | 15413 | `27DB236B…763C` |
  | `..._26072702_XAUUSD_H1.jsonl` | 6992 | `27E5DCB8…31D6` |
  | `..._26072703_EURUSD_H1.jsonl` | 15236 | `26C2FCE9…8A83` |

- **So sánh** baseline với từng lần candidate bằng `compare_execution_regression.py --require-diagnostics` và diff journal theo dòng (Net/PF/DD so khớp, không ghi giá trị):

  | | Lệnh (B/C) | Deal | Cycle | OrderSend | Net/PF/DD | Diagnostics | Diff journal |
  |---|---:|---:|---:|---:|---|---|---:|
  | Candidate lần 1 | 148 / 148 | 246 / 246 | 93 / 93 | 385 | giống hệt | equal | 3 dòng |
  | Candidate lần 2 | 148 / 148 | 246 / 246 | 93 / 93 | 385 | giống hệt | equal | 3 dòng |

  3 dòng khác đều được phép: dòng input `ExportPhase3OpportunityInTester` (false/true) và dòng `PHASE3 opportunity exporter initialized ... path=...phase3/tester/opportunities/...` chỉ có ở candidate.
- **File tester:** baseline không tạo file (đúng, cờ tắt). Candidate tạo `phase3/tester/opportunities/Mentor_RSI_MTF_26072626_BTCUSD_H1.jsonl`, 736 dòng, cả 736 dòng mang schema `phase3-opportunity-observation/1`. Lần chạy 2: vẫn 736 dòng, 1026705 byte, SHA-256 giống hệt lần 1 (bị ghi đè, không gấp đôi).
- **Kết luận:** đủ điều kiện §3 để đề xuất merge `fix/ea-tester-telemetry-isolation`. Report: `reports\parity\telem_v26_{base,cand,cand2}_2023.htm`; journal `journals\telem_v26_2023_*.log`; snapshot `runs\telem_live_{before,after}.json`. Không commit report thô hay nội dung JSONL. File tester (1 file trong `phase3/tester/`) để nguyên, không phải file live.
