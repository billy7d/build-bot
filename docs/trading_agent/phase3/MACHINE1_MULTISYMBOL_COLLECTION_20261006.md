# Máy 1 — Thu dữ liệu forward ETHUSD, XAUUSD, EURUSD H1 (2026-10-06)

Dành cho agent trên máy 1. Đọc toàn bộ trước khi chạy lệnh nào. Các nguyên tắc của
`MACHINE1_FORWARD_COLLECTION_HANDOFF_20261001.md` vẫn áp dụng: không nhập credential, không sửa EA,
không động vào Gate B/A1, không commit trong checkout runtime.

## 1. Mục đích và phạm vi

- Thu luồng `phase3-opportunity-observation/1` cho ba domain mới, làm dữ liệu forward cho Phase 4 (C2,
  `docs/trading_agent/PHASE4_ACCELERATED_LEARNING_DESIGN.md`).
- Dữ liệu sau mốc kiến thức của LLM là nguồn xác nhận sạch duy nhất (§6.6), nên thu càng sớm càng tốt.
- **Không** tính vào gate 500 mẫu của bundle hiện tại. Bundle chỉ được huấn luyện trên BTCUSD, nên
  không chạy collector Phase 3 cho các mã này. Thay vào đó, file JSONL được chụp snapshot có hash mỗi ngày.
- **Không** so sánh hiệu suất tài khoản thu dữ liệu với V26/V63. PnL của tài khoản này không phải bằng
  chứng forward.

```text
LIVE_TRADING=NO
EA_EXECUTION=DEMO_ONLY (tài khoản demo thứ ba, riêng cho thu dữ liệu)
EXECUTION_AUTHORITY=NONE (collector/snapshot)
```

## 2. Vì sao cần tài khoản demo riêng

- EA không có chế độ chỉ quan sát: `AllowLong`/`AllowShort=false` cũng tắt luôn tín hiệu shadow
  (`AuditShadowSignalsOnClosedBar`). Muốn có dữ liệu thì EA phải chạy với Algo Trading như V26.
- Nếu gắn lên tài khoản V26 hoặc V63, lệnh ETH/XAU/EUR sẽ làm sai DD, PF và các điều kiện dừng của mẫu
  forward đối chứng. Vì vậy **bắt buộc dùng tài khoản demo thứ ba**.
- Ba chart dùng chung một tài khoản là an toàn: EA chỉ quản lý position có đúng `_Symbol` và
  `MagicNumber` (`SelectedPositionIsManaged`).

## 3. Preset

Bản sao preset 83 (V26 + observer), giữ nguyên mọi tham số chiến lược, chỉ đổi:

| Preset | Symbol | MagicNumber | SHA-256 (byte-preserved, `-text`) |
|---|---|---|---|
| `outputs/presets/85_v26_data_ethusd_h1_p3obs.set` | ETHUSD | `26072701` | `21ae002537bf61b76bfc81f336d8ae1c07527827f796b1445ebd57bbf837d120` |
| `outputs/presets/86_v26_data_xauusd_h1_p3obs.set` | XAUUSD | `26072702` | `31ecff1b79ad05b3da9ac53840b71701ec34679e9d8f525197b9293b51d363aa` |
| `outputs/presets/87_v26_data_eurusd_h1_p3obs.set` | EURUSD | `26072703` | `34acce60621a2bc7cf72c11fca8c1bb40a7a4db882013fa268c88439a4d8a229` |

Khác preset 83 ở đúng 4 dòng: `MagicNumber`, và `ExportForwardTelemetryCsv`, `ExportDiagnosticsCsv`,
`ExportShadowSignalsCsv` = `false`. Ba file CSV này có tên cố định (`Mentor_RSI_MTF_forward.csv`, ...).
Với ba chart trong cùng terminal, chart thứ hai sẽ không mở được file và EA tự dừng ("refusing to run an
unmonitored forward preset"). Đây là các cờ chỉ phục vụ quan sát. JSONL opportunity và telemetry Phase 3
vẫn bật và có tên file riêng theo magic và symbol.

Tham số chiến lược được tinh chỉnh cho BTCUSD (ví dụ `SLBufferPoints=50` tính theo point của từng mã).
**Không chỉnh cho từng mã.** Việc đo chiến lược chuyển giao sang mã khác ra sao là một phần của kiểm kê
C2 (§5.2 thiết kế Phase 4).

## 4. Các bước

1. **Operator** mở một tài khoản demo mới cùng broker, balance `5,000 USD`, leverage `1:10` (đồng bộ
   điều kiện V26). Agent không tạo tài khoản và không nhập mật khẩu.
2. Cài terminal thứ ba, ví dụ `D:\Trading\MT5-DATA`, với data folder riêng. Không dùng chung terminal
   với V26/V63.
3. Kiểm tra repo `D:\Trading\buildbot` đang ở `main` có commit này, và SHA-256 của ba preset khớp §3.
4. Chép `outputs/Mentor_RSI_MTF_v1.mq5` vào `MQL5\Experts\` của terminal mới. Compile bằng MetaEditor
   của chính terminal đó (`0 errors, 0 warnings`). Ghi SHA-256 file `.ex5`. Chép ba preset vào
   `MQL5\Presets\`.
5. **Operator** đăng nhập tài khoản demo mới. Agent xác nhận đây là tài khoản demo trước khi đi tiếp
   (Journal hoặc tiêu đề cửa sổ). Không ghi số tài khoản hay tên server vào repo.
6. Kiểm tra tên symbol thật của broker (có thể có hậu tố, ví dụ `XAUUSD.m`). Nếu broker không có một mã,
   bỏ mã đó và ghi lại; không thay bằng mã khác.
7. Ghi **contract spec** từng mã (Symbol > Specification): contract size, digits, point, tick size,
   tick value, min lot, volume step, trading hours, spread hiện tại. Lưu vào
   `D:\Trading\build-bot-runtime\phase4-data\contract_specs_<yyyyMMdd>.json`. Đây là dữ liệu bắt buộc
   cho kiểm kê C2.
8. Mở ba chart **H1**, gắn EA và nạp đúng preset theo bảng §3. Đối chiếu Inputs: `MagicNumber`,
   `EntryTF=16385` (H1), `ShadowSignalMode=1`, `ExportPhase3OpportunityJsonl=true`.
9. **Operator** bật Algo Trading trên terminal `MT5-DATA`.
10. Kiểm tra Journal có log mở file opportunity cho từng chart, và file tồn tại:

    ```text
    %APPDATA%\MetaQuotes\Terminal\Common\Files\phase3\opportunities\Mentor_RSI_MTF_26072701_<ETH symbol>_H1.jsonl
    ...\Mentor_RSI_MTF_26072702_<XAU symbol>_H1.jsonl
    ...\Mentor_RSI_MTF_26072703_<EUR symbol>_H1.jsonl
    ```

11. Chạy snapshot thử một lần:

    ```powershell
    D:\Trading\buildbot\scripts\phase4\snapshot_opportunity_streams.ps1 -DestinationRoot D:\Trading\build-bot-runtime\phase4-data
    ```

    Script chỉ đọc file nguồn (share read/write, không chặn EA), copy vào
    `snapshots\<yyyyMMdd>\`, rồi ghi `snapshot_utc, file, size, line_count, sha256` vào
    `manifest.csv` (append-only). Chạy lại trong cùng ngày sẽ ghi đè bản copy của ngày đó, nhưng manifest
    vẫn giữ mọi dòng hash.

12. **Cần operator đồng ý:** tạo scheduled task chạy snapshot mỗi ngày, ví dụ lúc 00:30 giờ máy:

    ```powershell
    $action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "D:\Trading\buildbot\scripts\phase4\snapshot_opportunity_streams.ps1" -DestinationRoot "D:\Trading\build-bot-runtime\phase4-data"'
    $trigger = New-ScheduledTaskTrigger -Daily -At 00:30
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName 'BuildBot-Phase4-DataSnapshot' -Action $action -Trigger $trigger -Principal $principal
    ```

13. Thêm `MT5-DATA` vào cơ chế tự khởi động MT5 sau khi đăng nhập Windows, giống V26/V63.

## 5. Báo cáo về máy 2

Ghi `reports/trading_agent/phase3_forward_node_ops/machine1_multisymbol_collection_20261006.md` trên
branch `ops/machine1-forward-activation-20261001` (push từ clone báo cáo), gồm:

- tên symbol thật của từng mã, mã bị bỏ (nếu có) và lý do;
- SHA-256 preset, SHA-256 `.ex5`, thời điểm gắn EA (UTC);
- contract spec (không có số tài khoản/server);
- trạng thái scheduled task snapshot, và **số dòng** trong mỗi file sau 24 giờ đầu.

**Không** đưa nội dung JSONL, outcome hay PnL vào báo cáo.

## 6. Điều kiện dừng

- Không chứng minh được tài khoản là demo, hoặc EA bị gắn nhầm lên tài khoản/terminal V26/V63.
- Journal có `initialization failed` hoặc không mở được file opportunity.
- Hai chart cùng MagicNumber, hoặc một magic ghi ra symbol khác bảng §3.
- Sau 72 giờ, một mã vẫn có 0 dòng trong khi thị trường mở: dừng, kiểm tra, báo operator (có thể chiến
  lược không phát tín hiệu trên mã đó. Bản thân đây là một kết quả kiểm kê, không phải lý do để chỉnh
  tham số).

## 7. Đính chính: min lot không làm tròn lên (2026-10-06)

Báo cáo máy 1 ghi rằng với ETHUSD (min lot `0.1`) "lệnh ETH sẽ bị làm tròn lên mức tối thiểu". Điều này
không đúng với EA hiện tại. Trong `BuildRiskPlanForMoney` (và nhánh add của pyramiding), khi
`rawLots < minLot` EA gán `rp.lots = minLot` **chỉ để tính `actualRiskPct` cho chẩn đoán**, rồi
`return false` với lý do `raw_lot_below_min_lot`. Lệnh bị **bỏ**, không vào với min lot. Đây cũng là bất biến
trong README ("không ép lot lên min-lot vì điều đó phá vỡ risk budget").

Hệ quả cho phần thu dữ liệu:

- **Tín hiệu shadow và luồng opportunity không bị ảnh hưởng.** Đường audit shadow không đi qua risk plan
  nên vẫn ghi mọi tín hiệu, kể cả tín hiệu mà lệnh thật sẽ bị bỏ.
- **Tài khoản thu dữ liệu sẽ có ít lệnh thật hơn tín hiệu**, nhất là ETHUSD. Với `RiskPerTradePct=0.5`
  và equity `5,000 USD`, risk mong muốn là `25 USD`. Theo spec đã báo cáo (tick value = tick size = `0.01`,
  contract size `1`), `riskPerLot` bằng đúng khoảng cách SL (USD), nên `rawLots = 25 / khoảng cách SL`.
  Lệnh ETHUSD chỉ được mở khi khoảng cách SL `<= 250 USD` (`rawLots >= 0.1`).
  Với XAUUSD (min lot `0.01`) ngưỡng là `<= 25 USD`; với EURUSD (min lot `0.01`) là `<= 0.025` (250 pip).
  Các ngưỡng này chỉ đúng khi equity ở mức `5,000 USD`; equity đổi thì ngưỡng đổi theo.
- **Không chỉnh tham số, risk hay lot để "cho EA vào lệnh".** Đây vẫn là bài đo chiến lược chuyển giao sang
  mã khác ra sao (§5.2 thiết kế Phase 4).

Trong kiểm kê C2, mỗi domain báo cáo: số tín hiệu shadow, số lần `raw_lot_below_min_lot` (Journal hoặc CSV
chẩn đoán nếu bật lại), và tỷ lệ giữa hai số này. Domain có tỷ lệ bỏ lệnh cao được ghi `EXCLUDED` kèm lý do.
