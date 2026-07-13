# Mentor_RSI_MTF_v1 - Ghi chú triển khai

File đã cập nhật: `Mentor_RSI_MTF_v1.mq5`

## Đã triển khai

- Risk engine không ép lot lên `SYMBOL_VOLUME_MIN`. Nếu lot tính theo `RiskPerTradePct` nhỏ hơn lot tối thiểu, bot skip trade và log lý do `raw_lot_below_min_lot`.
- Bias đã tách khỏi entry: D1/H4/H1 dùng để tính bias, M15/H1 entry chỉ dùng timing theo `EntryTF`.
- Thêm `UseMTFBias` để chạy ablation test core RSI only.
- Entry được nối theo cơ chế armed setup: sau khi RSI chạm extreme, setup còn hiệu lực trong `LookbackExtremeBars`.
- Thêm `EntryMode`:
  - `RSI_CROSS_EMA`: logic chặt, cần RSI cross EMA9 gần đây.
  - `RSI_ABOVE_EMA_AFTER_EXTREME`: logic mở rộng, sau extreme chỉ cần RSI nằm đúng phía EMA9 và đang dốc đúng hướng.
- Thêm `MaxSetupAgeBars`: setup có thể sống 48 nến mặc định, tách khỏi `LookbackExtremeBars`.
- Entry mặc định đổi sang `RSI_ABOVE_EMA_AFTER_EXTREME` để tăng số lượng lệnh có kiểm soát.
- TP1 partial close tại `TP1_R`, sau đó kéo SL về entry.
- TP2 partial close theo RSI curl ngược trên EntryTF/H1.
- Full exit khi H4 RSI deteriorate.
- Đã bỏ toàn bộ filter và indicator baseline cũ. Bias, entry, exit, chop, trailing chỉ còn dùng RSI/EMA/WMA/ATR và giá/SL.
- Thêm diagnostic log mỗi nến entry TF: armed state, bias count, reject counters, snapshot RSI/EMA/WMA/ATR cho D1/H4/H1/M15.
- Thêm `DiagnosticsEveryBars` để giảm nhiều log và `ExportDiagnosticsCsv` để xuất file `Mentor_RSI_MTF_diag.csv` trong `MQL5/Files`.
- Thêm summary log `DIAG_SUMMARY` khi kết thúc backtest/deinit. Log summary được chia thành nhiều dòng ngắn (`core`, `rejects`, `pyramid`, `params`, `params2`) để tránh MT5 cắt mất phần cuối trong Journal.
- V4:
  - Thêm `LongArmLevel` và `ShortArmLevel` để arm setup rộng hơn mà vẫn giữ `Oversold/Overbought` cho exit cực trị.
  - Thêm `BiasMode`: `STRICT_COUNT` và `HTF_VETO`; mặc định `HTF_VETO` để tăng cơ hội vào lệnh có kiểm soát.
  - Bỏ long no-chase theo khoảng cách baseline cũ.
  - Thêm `TrailMode`: `OFF`, `ATR_CHANDELIER`; mặc định nên test `ATR_CHANDELIER`.
  - Thêm `ATRPeriod`, `TrailLookbackBars`, `TrailATRMultiplier`, `StartTrailingAfterR`, `RunnerMinPct` để giữ runner cho lệnh thắng lớn.
- V5:
  - Thêm `EntryMode=RSI_PULLBACK_CONTINUATION` để tăng tần suất lệnh trong core RSI MTF mà không thêm Volume/VWAP/Trap.
  - Thêm `PullbackLongLevel`, `PullbackShortLevel`, `PullbackLookbackBars`. Mode này chấp nhận setup nếu RSI gần đây pullback về vùng 50/50, sau đó RSI nằm đúng phía EMA9, EMA9 dốc đúng hướng, và RSI bar hiện tại cũng dốc đúng hướng.
  - Sửa quản lý lệnh để giữ `initial risk distance` riêng cho position. Trước đây sau khi SL được kéo về entry, R-multiple có thể bị tính lại theo SL mới, làm trailing/partial exit kích hoạt sai nhịp.
  - Diagnostic reject đã tính cả setup pullback, không chỉ tính setup armed từ extreme.

## File preset

Đã tạo các preset tại thư mục `outputs/presets`:

- `01_core_rsi_only.set`
- `02_core_rsi_mtf.set`
- `03_core_rsi_mtf_bias.set`
- `04_full_v1_filter.set`
- `05_expanded_35_65.set`
- `06_v4_core_htf_veto_no_trailing.set`
- `07_v4_htf_veto_atr_trailing_no_long_filter.set`
- `08_v4_htf_veto_atr_trailing_long_filter.set`
- `09_v4_40_60_more_trades_trailing.set`
- `10_v5_pullback_m15_trailing_balanced.set`
- `11_v5_pullback_h1_trailing_balanced.set`
- `12_v5_pullback_m15_rsi_only_filter.set`
- `13_v11_exit_trail_3p0_start_2p0.set`
- `14_v11_exit_trail_3p0_start_2p25.set`
- `15_v11_exit_trail_3p0_start_2p5.set`
- `16_v11_exit_trail_3p2_start_2p0.set`
- `17_v11_exit_trail_3p2_start_2p25.set`
- `18_v11_exit_trail_3p2_start_2p5.set`
- `19_v11_exit_trail_3p5_start_2p0.set`
- `20_v11_exit_trail_3p5_start_2p25.set`
- `21_v11_exit_trail_3p5_start_2p5.set`
- `22_v11_pyramid_control_off.set`
- `23_v11_pyramid_add1_r0p20.set`
- `24_v11_pyramid_add1_r0p30.set`
- `25_v11_pyramid_add2_r0p30_r0p15.set`

## Preset V4/V5 nên chạy độc lập

Mỗi preset là một cấu hình độc lập. Không cần chạy nối tiếp. Khi so sánh, giữ nguyên symbol, date range, deposit, leverage, commission, spread, modelling quality.

1. `06_v4_core_htf_veto_no_trailing.set`
   - Mục tiêu: đo riêng tác động của core RSI + bias mới.
2. `07_v4_htf_veto_atr_trailing_no_long_filter.set`
   - Mục tiêu: đo tác động của ATR trailing trên core RSI + HTF_VETO.
3. `08_v4_htf_veto_atr_trailing_long_filter.set`
   - Preset legacy từ bản có long filter cũ; sau khi bỏ baseline filter, cấu hình này có thể trùng với `07`.
4. `09_v4_40_60_more_trades_trailing.set`
   - Mục tiêu: tăng số lệnh nếu 35/65 vẫn dưới 60 trades.
5. `10_v5_pullback_m15_trailing_balanced.set`
   - Mục tiêu: tăng số lệnh bằng RSI pullback/continuation trên M15, vẫn giữ HTF_VETO, chop filter, ATR trailing.
6. `11_v5_pullback_h1_trailing_balanced.set`
   - Mục tiêu: kiểm tra cùng logic pullback nhưng timing trên H1 để giảm nhiễu và so sánh Long/Short.
7. `12_v5_pullback_m15_rsi_only_filter.set`
   - Mục tiêu: bản pullback M15 tối giản hơn, chỉ giữ RSI MTF + chop + ATR trailing.

## Tối ưu exit-only V11

V11 là baseline H1 pullback có kết quả tốt nhất trong vòng review hiện tại. Nhóm preset `13` đến `21` giữ nguyên toàn bộ entry/risk/bias của `11_v5_pullback_h1_trailing_balanced.set`, chỉ thay đổi:

- `TrailATRMultiplier`: `3.0`, `3.2`, `3.5`
- `StartTrailingAfterR`: `2.0`, `2.25`, `2.5`

Mục tiêu vòng này là tìm exit tốt hơn trước khi tối ưu `LongArmLevel`, `ShortArmLevel`, `MaxSetupAgeBars`. Không nên optimize entry và trailing cùng lúc ở vòng đầu vì sẽ khó biết lợi nhuận đến từ tín hiệu vào lệnh hay cách thoát lệnh.

Thứ tự test để đọc kết quả:

1. Chạy lại `11_v5_pullback_h1_trailing_balanced.set` làm baseline.
2. Chạy độc lập `13` đến `21` trên cùng symbol/date/deposit/leverage/spread/modelling.
3. Ghi lại Net Profit, Profit Factor, Expected Payoff, Equity DD max, tổng trade, long/short, largest profit contribution, và `DIAG_SUMMARY`.
4. Chỉ chọn preset nếu PF >= `1.20`, Expected Payoff dương, Equity DD max <= `12%`, số lệnh không giảm quá mạnh so với V11, và OOS 2024-01-01 đến 2026-07-01 không âm nặng.

Nếu có nhiều preset đạt điều kiện, ưu tiên preset có `Net Profit / Equity DD max` cao hơn V11 và largest profit không chiếm tỷ trọng quá lớn trong gross profit.

## V6 profit-funded pyramiding (netting và hedging)

Pyramiding được thêm để tăng exposure chỉ sau khi lệnh gốc đã đi đúng hướng. Mặc định `UsePyramiding=false`; khi tắt, hành vi EA giữ nguyên như V11/V13-V21.

`PyramidAccountMode` có ba chế độ: `PYRAMID_AUTO`, `PYRAMID_NETTING`, `PYRAMID_HEDGING_GROUP`. Mặc định `PYRAMID_AUTO`: nếu tài khoản là netting thì quản lý một position gộp; nếu tài khoản là hedging thì quản lý cả cụm ticket cùng `Symbol + MagicNumber`.

Trên hedging account, mỗi base/add là một position riêng. EA lưu ticket và `POSITION_IDENTIFIER` của từng leg, đồng bộ volume theo ticket, dời SL cho toàn bộ group, đóng toàn bộ group khi H4 exit hoặc khi post-fill risk violation, và dùng `DEAL_POSITION_ID` để trừ đúng leg khi có deal đóng lệnh.

Một cycle lưu các leg với giá/volume từng lần vào lệnh. Khi partial close xảy ra, volume được trừ theo ticket/identifier trên hedging hoặc FIFO trên netting, và P/L đã đóng được cộng từ `OnTradeTransaction`. Trước mỗi add, EA tính:

`bundle stop P/L = realized net P/L + sum(OrderCalcProfit của mỗi leg tại shared SL)`

Điều kiện bắt buộc trước khi gửi add:

`bundle stop P/L - add risk - cost reserve >= min locked profit`

Cost reserve mặc định là `0.15R` và bao gồm dự phòng spread/slippage/chi phí của các leg đang mở. Sau fill, EA tính lại theo giá fill thực; nếu vi phạm ngưỡng locked profit, EA đóng toàn bộ group ngay và tăng diagnostic `pyrPostFillViolation`.

### Các tầng mặc định

| Tầng | Trigger từ base entry | Shared SL floor | Add risk | Ghi chú |
|---|---:|---:|---:|---|
| Add 1 | `+2.0R` | `+0.75R` | `0.30R` | Chỉ mở nếu RSI/EMA và HTF veto vẫn đồng thuận |
| Add 2 | `+3.5R` | `+1.75R` | `0.15R` | Chỉ bắt đầu sau khi Add 1 đã qua kiểm định |

Trailing vẫn dùng một shared SL và chỉ được đi theo chiều bảo vệ lợi nhuận. Trên hedging, shared SL được áp vào từng ticket trong group. Sau add đầu tiên, TP1/TP2 partial bị tắt cho phần còn lại của cycle; thoát group bằng shared trailing hoặc H4 RSI exit. EA cũng chặn add nếu spread > `0.10R`, equity DD từ peak >= `8%`, margin level < `500%`, không đủ free margin, RSI quá mua/quá bán theo `PyramidLongRSIMax`/`PyramidShortRSIMin`, hoặc lot add nằm dưới minimum.

Lưu ý quan trọng về lot: với base `0.01` và volume step `0.01`, Add 1 với risk `0.30R` thường sẽ tính ra dưới `0.01` lot và bị skip đúng chủ ý. Không được ép nó lên min lot. Để kiểm tra tính năng add với `RiskPerTradePct=0.5`, cần deposit lớn hơn hoặc symbol BTC có volume step nhỏ hơn; tất cả preset phải giữ cùng deposit/symbol để so sánh công bằng.

### Thứ tự test chống overfit

1. Hoàn thành V13-V21 và chọn trailing winner bằng Development 2019-2022, Validation 2023-2024. Không chọn chỉ theo Net Profit.
2. Thay `TrailATRMultiplier` và `StartTrailingAfterR` của preset 22-25 bằng trailing winner, sau đó không sửa hai tham số này trong vòng pyramiding.
3. Chạy `22` control, sau đó `23` (một add `0.20R`) và `24` (một add `0.30R`) độc lập. Không chạy `25` nếu cả 23/24 không qua gate.
4. Chỉ chạy `25` hai add nếu một add đạt PF >= `1.20`, Expected Payoff dương, DD <= `12%`, Pseudo-OOS 2025-2026 không âm nặng và `pyrPostFillViolation=0`.
5. So sánh theo PF, Expected Payoff, DD, OOS, long/short, largest cycle contribution. Không chọn một preset đơn lẻ vượt trội nếu hai preset lân cận suy giảm rõ ràng.

`DIAG_SUMMARY pyramid` bao gồm: `cycles`, `add1`, `add2`, `skipLocked`, `skipMinLot`, `skipSpread`, `skipMargin`, `stopModifyFail`, `postFillViolation`, `worstStopPnLR`. `DIAG_SUMMARY params2` có thêm `PyramidAccountMode` và `ActivePyramidMode` để xác nhận EA đang chạy netting hay hedging group.

## Preset backtest ưu tiên

Chạy trên BTCUSD trước, cùng một giai đoạn report cũ nếu có thể:

1. Core RSI only
   - `UseMTFBias=false`
   - `UseChopFilter=false`
   - `EntryMode=RSI_ABOVE_EMA_AFTER_EXTREME`

2. Core RSI + MTF
   - `UseMTFBias=true`
   - `MinAlignedTimeframes=2`
   - `UseChopFilter=false`
   - `EntryMode=RSI_ABOVE_EMA_AFTER_EXTREME`

3. Core RSI + MTF legacy
   - `UseMTFBias=true`
   - `MinAlignedTimeframes=2`
   - `UseChopFilter=false`
   - `EntryMode=RSI_ABOVE_EMA_AFTER_EXTREME`
   - Sau khi bỏ baseline filter, preset này có thể trùng với Core RSI + MTF.

4. Full v1 filter
   - `UseMTFBias=true`
   - `MinAlignedTimeframes=2`
   - `UseChopFilter=true`
   - `EntryMode=RSI_ABOVE_EMA_AFTER_EXTREME`

## Matrix tối ưu tối thiểu

- `EntryTF`: M15, H1
- `LookbackExtremeBars`: 12, 24, 48
- `MaxSetupAgeBars`: 24, 48, 72
- `MaxBarsAfterCross`: 2, 5, 8
- `PullbackLongLevel/PullbackShortLevel`: 48/52, 50/50, 52/48
- `PullbackLookbackBars`: 12, 24, 48
- `MinAlignedTimeframes`: 2, 3
- `Oversold/Overbought`: 30/70, 35/65, 40/60
- `BiasMode`: HTF_VETO, STRICT_COUNT
- `EntryMode`: RSI_ABOVE_EMA_AFTER_EXTREME, RSI_PULLBACK_CONTINUATION
- `TrailMode`: OFF, ATR_CHANDELIER
- `TrailATRMultiplier`: 2.5, 3.0, 3.5
- `StartTrailingAfterR`: 1.5, 2.0, 2.5

Chỉ xem cấu hình là ứng viên nếu có tối thiểu 60 lệnh, Profit Factor >= 1.20, Expected Payoff dương, Equity DD <= 12%, Long PF >= 1.0 hoặc Long winrate không kém Short quá 10 điểm phần trăm.

## Môi trường compile và backtest tự động

Dự án dùng trực tiếp MetaEditor, terminal và local Strategy Tester trong Wine prefix hiện có trên macOS. Quy trình này giữ nguyên dữ liệu BTCUSD, cấu hình broker và lịch sử tick đã tải; không tạo một MT5 độc lập có dữ liệu khác.

- `tools/mt5/compile.sh`: compile EA, bắt buộc `0 errors, 0 warnings`, sau đó đồng bộ `.mq5` và `.ex5` vào thư mục `MQL5/Experts/Advisors` của MT5.
- `tools/mt5/backtest.sh`: chạy một preset bằng cấu hình Strategy Tester cố định và tự lưu report, preset, cấu hình test, tóm tắt chỉ số cùng `DIAG_SUMMARY source=OnTester`.
- `tools/mt5/run_batch.sh`: compile một lần rồi chạy tuần tự nhiều preset cùng điều kiện test.
- `tools/mt5/report_summary.py`: đọc report HTML UTF-16 của MT5, tính các chỉ số chính, Long/Short PF theo deals và tỷ trọng largest profit trade trong gross profit.

Kết quả tự động được lưu tại `backtests/<tên-run>/`. MT5 giao diện phải đóng trước khi chạy vì terminal dòng lệnh dùng cùng Wine prefix; script sẽ từ chối chạy nếu phát hiện `terminal64.exe` đang mở. Hướng dẫn lệnh chi tiết nằm trong `tools/mt5/README.md`.

Kiểm thử hạ tầng ngày 2026-07-13 đã compile thành công với `0 errors, 0 warnings`. Backtest V22 tự động trên Development 2019-01-01 đến 2022-12-31 khớp baseline đã chạy thủ công: Net Profit `+8.55`, Profit Factor `1.02`, Expected Payoff `+0.04`, Equity DD max `11.39%` và `205` trades.

## Cập nhật quản lý stop cho pyramiding

Sau khi test V22, V23 và V24 với deposit 5,000 USD trên giai đoạn Development 2019-01-01 đến 2022-12-31, log cho thấy `stopModifyFail` cao dù retcode MT5 là `10009 done`. Nguyên nhân là EA có thể xem một mức SL là cải thiện bằng so sánh số thực thô, nhưng sau khi normalize theo `_Digits` thì mức SL đó không còn thay đổi thực tế.

Đã làm gọn logic modify stop cho pyramiding:

- Chuẩn hóa `targetSL` và `currentSL` trước khi so sánh.
- Chỉ gửi `PositionModify` nếu SL cải thiện tối thiểu một tick-size/point.
- Kiểm tra khoảng cách stops/freeze trước khi gọi trade server.
- Tách `stopModifySkip` cho trường hợp không thể modify hợp lệ, còn `stopModifyFail` chỉ phản ánh lỗi modify thật sau khi đã qua điều kiện hợp lệ.

Kiểm thử lại ngày 2026-07-13 với deposit 5,000 USD:

- V23 `Add1RiskR=0.20`: Net Profit `+160.31`, Profit Factor `1.07`, Equity DD `7.85%`, `327` trades, `add1=11`, `stopModifyFail=0`.
- V24 `Add1RiskR=0.30`: Net Profit `+154.39`, Profit Factor `1.07`, Equity DD `8.50%`, `332` trades, `add1=15`, `stopModifyFail=0`.
- Hai preset giữ nguyên kết quả giao dịch so với trước khi sửa, nhưng loại bỏ nhiễu `stopModifyFail` do so sánh SL dưới tick-size.

## Vòng test V26-V28 từ V23 sạch

V23 được chọn làm candidate pyramid sạch vì `Add1RiskR=0.20` giữ DD thấp hơn V24 và sau khi sửa stop-management đã có `stopModifyFail=0`. V26-V28 giữ nguyên toàn bộ core RSI, bias, trailing, risk và `Add1RiskR=0.20`; chỉ thay đổi trigger hoặc lock floor của add đầu tiên.

- `26_v23_add1_trigger_2p25_lock_0p75.set`: dời Add 1 muộn hơn từ `2.00R` lên `2.25R`, giữ lock floor `0.75R`.
- `27_v23_add1_trigger_2p50_lock_0p75.set`: dời Add 1 muộn hơn từ `2.00R` lên `2.50R`, giữ lock floor `0.75R`.
- `28_v23_add1_trigger_2p00_lock_1p00.set`: giữ Add 1 tại `2.00R`, nhưng siết lock floor từ `0.75R` lên `1.00R`.

Mục tiêu đọc kết quả:

- Nếu V26/V27 tốt hơn V23, add muộn hơn đang giảm nhiễu và tránh chồng lệnh quá sớm.
- Nếu V28 tốt hơn V23, vấn đề chính là cần khóa lợi nhuận gốc chặt hơn trước khi cho phép add.
- Nếu cả ba không vượt V23, giữ V23 làm candidate và chuyển sang kiểm tra OOS hoặc tối ưu điều kiện RSI của `PyramidSignal`.

Kết quả Development 2019-01-01 đến 2022-12-31, deposit 5,000 USD:

| Preset | Net Profit | Profit Factor | Expected Payoff | Equity DD | Trades | Add 1 | Long PF | Short PF | Ghi chú |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| V23 | `+160.31` | `1.07` | `0.49` | `7.85%` | `327` | `11` | `0.91` | `1.22` | Candidate gốc |
| V26 | `+191.44` | `1.09` | `0.59` | `8.10%` | `324` | `7` | `0.91` | `1.26` | Trigger `2.25R` tốt hơn V23 |
| V27 | `+189.02` | `1.09` | `0.59` | `8.11%` | `321` | `4` | `0.92` | `1.25` | Trigger `2.50R` bắt đầu bỏ lỡ add |
| V28 | `+192.47` | `1.09` | `0.58` | `7.67%` | `330` | `12` | `0.90` | `1.26` | Lock floor `1.00R` tốt nhất trên Development |

V28 là winner trên Development vì Net Profit cao nhất, Equity DD thấp nhất, largest profit contribution thấp hơn V23 và `stopModifyFail=0`. V26 là ứng viên phụ vì cải thiện mạnh so với V23 với số add ít hơn, phù hợp để kiểm tra thêm tính ổn định. Bước chống overfit tiếp theo là chạy Validation 2023-01-01 đến 2024-12-31 cho V23, V26 và V28 trước khi chọn preset chính.

Kết quả Validation 2023-01-01 đến 2024-12-31, deposit 5,000 USD:

| Preset | Net Profit | Profit Factor | Expected Payoff | Equity DD | Trades | Add 1 | Long PF | Short PF | Ghi chú |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| V23 | `+283.89` | `1.10` | `0.69` | `6.82%` | `411` | `5` | `1.44` | `0.90` | Baseline pyramid sạch |
| V26 | `+309.34` | `1.11` | `0.76` | `6.55%` | `409` | `5` | `1.46` | `0.90` | Tốt nhất trên Validation |
| V28 | `+262.79` | `1.09` | `0.63` | `6.96%` | `418` | `7` | `1.41` | `0.89` | Thắng Development nhưng yếu hơn Validation |

Kết quả Pseudo-OOS 2025-01-01 đến 2026-07-01, deposit 5,000 USD:

| Preset | Net Profit | Profit Factor | Expected Payoff | Equity DD | Trades | Add 1 | Long PF | Short PF | Ghi chú |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| V23 | `+88.35` | `1.03` | `0.26` | `6.37%` | `334` | `4` | `0.93` | `1.12` | Dương nhưng yếu |
| V28 | `+84.76` | `1.03` | `0.25` | `6.65%` | `336` | chưa xác nhận từ summary | `0.94` | `1.11` | Dương nhưng kém V23 |
| V26 | `+106.31` | `1.04` | `0.32` | `5.78%` | `330` | `2` | `0.95` | `1.12` | Tốt nhất OOS trong nhóm V23/V26/V28 |

Kết luận sau rerun sạch: V26 là baseline pyramid chính thức cho vòng tiếp theo. V26 thắng V23 ở Development, Validation và Pseudo-OOS; Net Profit và Expected Payoff cao hơn, Equity DD thấp hơn ở Validation/OOS, `stopModifyFail=0`, `postFillViolation=0`. Tuy nhiên Profit Factor OOS vẫn chỉ `1.04`, nên vòng tiếp theo không nên tăng risk; cần tiếp tục cải thiện chất lượng tín hiệu, đặc biệt Long PF OOS vẫn dưới `1.0`. V28 bị loại khỏi vị trí winner vì yếu hơn V23/V26 ở Validation và không hơn V23 ở OOS.

## Lưu ý quan trọng

Với BTCUSD và tài khoản 1,000 USD, broker có thể bắt lot tối thiểu 0.01. Nếu risk 0.5% quá nhỏ, bot sẽ skip nhiều lệnh. Để test đúng risk engine, hãy so sánh:

- Tăng initial deposit trong tester.
- Hoặc tăng `RiskPerTradePct` tạm thời để kiểm tra logic entry/exit.
- Hoặc dùng symbol/account có lot step nhỏ hơn.
