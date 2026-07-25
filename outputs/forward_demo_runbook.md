# Runbook forward demo V26 đối chứng V63

## Trạng thái được phép

- V26 là baseline forward duy nhất. Dùng preset `outputs/presets/79_v26_forward_demo.set`, MagicNumber `26072626`.
- V63 chỉ là challenger. Dùng preset `outputs/presets/80_v63_forward_demo.set`, MagicNumber `26072663`.
- Chỉ chạy demo. Không gắn hai preset này vào tài khoản có tiền thật.
- V26 và V63 phải chạy trên hai tài khoản demo và hai terminal/data-folder riêng. Không dùng chung một tài khoản netting.
- Mỗi tài khoản bắt đầu với `5,000 USD`, leverage `1:10`, risk `0.5%`, cùng broker và cùng BTCUSD dự định dùng khi live.

## 1. Khóa bản build

1. Chép `outputs/Mentor_RSI_MTF_v1.mq5` vào đúng terminal của từng tài khoản.
2. Compile bằng MetaEditor của chính terminal/broker đó. Chỉ tiếp tục khi có `0 errors, 0 warnings`.
3. Nạp đúng preset V79 cho tài khoản V26 và V80 cho tài khoản V63.
4. Xác nhận trên Inputs:
   - `RiskPerTradePct=0.5`.
   - `EntryQualityGateMode=0`.
   - `VolatilityRiskMode=0`.
   - `ShortWideSLRiskMode=0`.
   - `ShadowSignalMode=1`, `MarketStateShadowMode=1`.
   - `ExportDiagnosticsCsv=true`, `ExportForwardTelemetryCsv=true`.
5. Ghi SHA-256 của source và preset vào nhật ký triển khai. Trên Windows PowerShell:

```powershell
Get-FileHash .\Mentor_RSI_MTF_v1.mq5 -Algorithm SHA256
Get-FileHash .\79_v26_forward_demo.set -Algorithm SHA256
Get-FileHash .\80_v63_forward_demo.set -Algorithm SHA256
```

Không sửa source/preset trong suốt mẫu. Sửa instrumentation tạo build mới; sửa execution tạo phiên bản và mẫu forward mới, không hồi tố.

## 2. Kiểm tra tài khoản và symbol

Trước khi bật AutoTrading, mở `Mentor_RSI_MTF_forward.csv` tại `File > Open Data Folder > MQL5 > Files`. Dòng `INIT` phải có đúng MagicNumber, symbol và ghi được:

- contract size;
- min lot và volume step;
- tick size và tick value;
- leverage;
- bid/ask và spread points lúc khởi tạo.

Hai terminal phải có cùng thông số hợp đồng. Nếu khác, dừng và không coi hai mẫu là đối chứng. Xác nhận balance ban đầu `5,000 USD`, leverage `1:10` và tài khoản là demo.

## 3. Smoke audit-on/audit-off

Smoke chuẩn đã chạy trên BTCUSD H1, 2026-06-01 đến 2026-06-30, 5,000 USD, leverage 1:10, 100% real ticks:

| Hệ thống | Audit | Net | PF | Equity DD | MT5 trades | Closed cycles |
|---|---|---:|---:|---:|---:|---:|
| V26 | OFF | `13.32` | `1.11` | `1.91%` | `13` | `11` |
| V26/V79 | ON | `13.32` | `1.11` | `1.91%` | `13` | `11` |
| V63 | OFF | `27.08` | `1.28` | `1.29%` | `14` | `11` |
| V63/V80 | ON | `27.08` | `1.28` | `1.29%` | `14` | `11` |

Summary và toàn bộ diagnostic execution đã khớp tuyệt đối cho từng cặp. Nếu compile trên terminal mục tiêu cho kết quả khác, không bật forward cho tới khi giải thích được khác biệt broker/data/spec.

## 4. Khởi động mẫu forward

1. Bắt đầu hai tài khoản cùng ngày, mỗi EA trên chart BTCUSD H1 riêng.
2. Bật Algo Trading và kiểm tra Journal có `FORWARD telemetry initialized`.
3. Xác nhận file telemetry xuất hiện, có `INIT`, đúng MagicNumber và tiếp tục có `HEARTBEAT`.
4. Ghi ngày bắt đầu chính thức. Chỉ tính base trade đã đóng hoàn toàn (`closed_cycles`), không dùng MT5 Total Trades vì partial exit/pyramid làm tăng số deal.
5. Không đổi ER20, ATR-rank, spread filter, SL/TP/trailing, pyramid, risk hoặc entry trong thời gian forward.

Telemetry critical được append và flush sau mỗi event. Peak equity được lưu thêm bằng terminal Global Variable theo symbol + MagicNumber, nên DD không reset khi EA/terminal restart; file mới sẽ khởi tạo lại peak cho mẫu mới. Diagnostic/shadow CSV cũng append qua các lần restart trên terminal live; Strategy Tester vẫn tạo file riêng cho từng run. Trước lần chạy đầu, archive hoặc xóa file cũ trong đúng data-folder để mẫu bắt đầu sạch. Không xóa file của terminal còn lại.

## 5. Theo dõi hàng tuần

Mỗi tuần, với từng terminal:

1. Xuất report HTML của toàn bộ Account History kể từ ngày bắt đầu.
2. Sao lưu các file sau từ `MQL5/Files` vào thư mục tuần tương ứng:
   - `Mentor_RSI_MTF_forward.csv`;
   - `Mentor_RSI_MTF_diag.csv`;
   - `Mentor_RSI_MTF_shadow_signals.csv`;
   - Journal/Experts log chứa toàn bộ dòng `DIAG_SUMMARY` và lỗi EA.
3. Tạo summary:

```bash
python tools/mt5/report_summary.py --json account-report.html > summary.json
```

4. Chạy gate. Nếu report live không có trường Period, truyền ngày bắt đầu và ngày chốt report:

```bash
python tools/mt5/forward_gate.py gate \
  --stage stage1 \
  --summary summary.json \
  --telemetry Mentor_RSI_MTF_forward.csv \
  --journal expert-journal.txt \
  --start-date 2026-07-20 \
  --end-date 2026-10-18
```

Exit code `0=PASS`, `2=WAIT`, `3=FAIL`. Công cụ hiển thị PF, expectancy, DD, concentration, net sau stress chi phí, median/p95 spread-R và slippage-R, order/risk rejects và lỗi dữ liệu.

Ghi kết quả vào `outputs/forward_weekly_log_template.csv`. Theo dõi riêng V26/V63; không cộng hoặc trộn vị thế/kết quả.

## 6. Pause tức thời

Tắt Algo Trading trên đúng terminal bị ảnh hưởng và giữ nguyên dữ liệu nếu có một trong các điều kiện:

- equity DD chạm `8%`;
- event `POST_FILL_VIOLATION`;
- event `STOP_MODIFY_FAIL` hoặc stop sau fill không hợp lệ;
- `actual_risk_money` vượt `desired_risk_money`;
- thiếu dữ liệu/state, initialization failure hoặc disconnect chưa reconnect.

Order reject, raw-lot dưới min-lot và reconnect đã phục hồi chưa tự động làm hỏng mẫu, nhưng phải phân loại trong tuần xảy ra. Không tăng risk để bù lệnh bị min-lot chặn.

## 7. Cổng quyết định

Stage 1 chỉ được đánh giá khi đồng thời đủ `90 ngày` và `60 closed cycles` cho từng hệ thống. Đi tiếp nếu PF `>=0.95`, DD `<8%`, dữ liệu đầy đủ và không có lỗi risk/stop.

Stage 2 chạy đến khi đồng thời đủ `180 ngày` và `120 closed cycles`:

```bash
python tools/mt5/forward_gate.py gate --stage stage2 \
  --summary summary.json --telemetry Mentor_RSI_MTF_forward.csv --journal expert-journal.txt \
  --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

Chỉ cân nhắc micro-live khi gate sau trả `PASS`:

```bash
python tools/mt5/forward_gate.py gate --stage micro \
  --summary summary.json --telemetry Mentor_RSI_MTF_forward.csv --journal expert-journal.txt \
  --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

Gate micro yêu cầu PF `>=1.10`, expectancy dương, DD dưới ngưỡng pause, largest-profit/gross `<5%`, top-3/gross `<=12%` và net vẫn dương sau khi cộng thêm `0.5×` chi phí spread/slippage đo được, tức stress tổng lên `1.5×`.

So sánh challenger sau khi hai mẫu đủ tuổi:

```bash
python tools/mt5/forward_gate.py compare \
  --baseline v26-summary.json \
  --candidate v63-summary.json
```

V63 chỉ có thể thay V26 nếu PF hơn ít nhất `0.10`, DD không cao hơn quá `1 điểm %`, Long PF và Short PF đều `>=1.0`, số cycles ít nhất `80%` V26 và vẫn đạt yêu cầu mẫu tối thiểu. Không tự động thay preset khi tool báo PASS; quyết định thay baseline phải được ghi thành một lần review riêng.

Nếu cả hai PF `<1.0` sau 120 closed cycles, dừng đường live. Không tăng risk và không quét lại threshold trên mẫu forward.

## 8. Nghiên cứu sau 60 trades

Chỉ sau 60 closed cycles mới dùng dữ liệu để phân loại vấn đề là entry, Short engine hay execution. Hướng tiếp theo ưu tiên:

1. Short engine có cấu trúc khác, không tiếp tục tinh chỉnh ngưỡng RSI đối xứng hiện tại; hoặc
2. đa dạng hóa symbol với một mẫu nghiên cứu độc lập.

Không dùng dữ liệu đang forward để sửa preset V26/V63 rồi tiếp tục cộng trades vào cùng mẫu.
