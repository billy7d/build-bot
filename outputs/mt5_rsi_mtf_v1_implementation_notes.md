# Mentor_RSI_MTF_v1 - Ghi chú triển khai

File đã cập nhật: `Mentor_RSI_MTF_v1.mq5`

## Bàn giao nhanh cho Codex trên Windows - đọc phần này trước

Cập nhật trạng thái: `2026-07-16`. Phần từ mục `Đã triển khai` trở xuống là lịch sử đầy đủ. Khi tiếp tục nghiên cứu, không cần khởi động lại từ V1 hoặc chạy lại toàn bộ preset cũ; hãy dùng trạng thái khóa dưới đây.

### Trạng thái khóa hiện tại

- EA chính: `outputs/Mentor_RSI_MTF_v1.mq5`.
- Baseline chính thức: `outputs/presets/26_v23_add1_trigger_2p25_lock_0p75.set`, gọi tắt là V26. Tên file có chữ V23 vì lý do lịch sử, nhưng tham số bên trong là V26: `Add1TriggerR=2.25`, `Add1LockFloorR=0.75`.
- Candidate nghiên cứu, chưa được dùng làm baseline/live: `outputs/presets/63_v30_d1_early_veto.set`, gọi tắt là V63.
- EA hiện compile sạch: `0 errors, 0 warnings`.
- V26/V63 giữ `RiskPerTradePct=0.5`, BTCUSD H1, deposit test 5,000 USD, leverage 1:10, real ticks khi dữ liệu cho phép.
- Không dùng BL, Volume, VWAP hoặc Trap. Không tăng risk để bù edge yếu.
- Risk engine, SL, partial exit, trailing và pyramiding đang ổn định; vòng nghiên cứu tiếp theo không được chỉnh các phần này.

| Mốc so sánh | PF | Equity DD | Trades | Long PF | Short PF | Largest/Gross | Top-3/Gross |
|---|---:|---:|---:|---:|---:|---:|---:|
| V26 Validation 2023-2024 | `1.11` | `6.55%` | `409` | `1.46` | `0.90` | `2.95%` | `10.36%` |
| V26 OOS 2025-2026 | `1.04` | `5.78%` | `330` | `0.95` | `1.12` | `3.56%` | chưa ghi |
| V63 Validation 2023-2024 | `1.23` | `5.90%` | `368` | `1.58` | `1.03` | `2.90%` | `10.16%` |
| V63 OOS 2025-2026 | `1.14` | `6.17%` | `278` | `0.97` | `1.27` | `4.13%` | `11.32%` |

Kết luận khóa: V63 tăng PF tổng và vẫn giữ DD/concentration tốt, nhưng Long/Short còn lệch nên chưa thay V26. V26 tiếp tục là baseline duy nhất.

Lưu ý môi trường Windows:

- Luôn dùng đường dẫn tương đối từ repo như `outputs/...`; không dùng lại đường dẫn tuyệt đối `/Users/...` của máy macOS.
- Các script `tools/mt5/*.sh` hiện phục vụ macOS/Wine. Trên Windows có thể dùng MetaEditor/Strategy Tester trực tiếp hoặc viết wrapper PowerShell tương đương; không sửa EA chỉ để phù hợp wrapper.
- `tools/mt5/report_summary.py` dùng Python chuẩn và có thể tái sử dụng trên Windows để validate/tóm tắt report HTML.
- Khi tự động hóa Windows, vẫn phải áp dụng cùng cổng report: đúng Expert/Symbol/period/date, bars/ticks lớn hơn 0, có `Test passed` và `DIAG_SUMMARY core source=OnTester`.
- Compile lại `.mq5` thành `.ex5` trên đúng terminal/broker Windows trước mỗi batch. Không dùng `.ex5` cũ được mang từ máy khác.

### Phát hiện phải giữ nguyên khi nghiên cứu tiếp

- EA chỉ quản lý một base position/pyramid group tại một thời điểm.
- Khi đang flat, `OnTick()` kiểm tra Long trước rồi mới kiểm tra Short. Nếu Long mở thành công, Short cùng nến không được mở.
- Khi đã có vị thế, vòng entry return sớm; EA hiện không đánh giá và không ghi lại tín hiệu Long/Short xuất hiện trong thời gian vị thế đang mở.
- V58 Long-only cho PF `1.29` trên Validation và `1.07` trên OOS. V60 Long-only có PF `1.47` và `1.13` nhưng ít trades và concentration cao hơn.
- V59 Short-only chỉ có PF `0.79` năm 2023 và `0.73` năm 2024. Short trong bản ghép tốt hơn vì một số vị thế Long đã chặn short yếu.
- Trên OOS, Long-only V58 PF `1.07` nhưng Long PF trong V26 ghép chỉ `0.95`; vị thế Short cũng chặn một phần long có lợi.
- Vì vậy PF từng chiều trong report ghép không phải edge độc lập. Cần đo tín hiệu bị chặn trước khi thay đổi thứ tự Long/Short hoặc đóng/reverse vị thế.

### Mục tiêu vòng tiếp theo

Xác định bằng dữ liệu:

1. Có bao nhiêu tín hiệu Long/Short hợp lệ xuất hiện cùng một nến khi tài khoản đang flat.
2. Có bao nhiêu tín hiệu cùng chiều hoặc ngược chiều xuất hiện khi một vị thế đang mở.
3. Tín hiệu bị chặn có edge hay không theo hướng đi tiếp: hit `+1R` hay `-1R`, MFE/MAE và forward return sau 6/12/24/48 nến H1.
4. Sau khi có dữ liệu audit, cơ chế nào hợp lý hơn: Long-first hiện tại, Short-first, ưu tiên theo regime, hay bỏ qua khi xung đột.

Không được chuyển ngay sang reverse position hoặc đóng lệnh đang chạy chỉ vì có tín hiệu ngược. Đây là thay đổi lớn về exit/risk và chỉ được xem xét nếu shadow data chứng minh edge rõ ràng.

### Thiết kế kỹ thuật V65-V66: shadow signal chỉ quan sát

Thêm input, mặc định tắt để preset cũ không đổi:

- `ShadowSignalMode=SHADOW_OFF`.
- `SHADOW_AUDIT_EVENTS`: ghi tín hiệu và outcome, không gửi lệnh ảo/thật.
- `ShadowForwardBars=48`; các checkpoint cố định là 6/12/24/48 nến, không đưa thành dải optimize ở vòng đầu.
- `ExportShadowSignalsCsv=true/false`.

Tạo tracker shadow độc lập với `armedLongBars`, `armedShortBars`, fan tracker và trạng thái live. Không gọi `UpdateArmedState()` của live khi vị thế đang mở, vì điều này có thể thay đổi entry thật sau khi lệnh đóng. Audit ON và OFF bắt buộc tạo cùng một lịch sử lệnh thật.

Mỗi nến EntryTF đã đóng, kể cả khi có vị thế, shadow engine phải:

1. Build D1/H4/H1/M15/EntryTF state từ nến đóng.
2. Cập nhật armed/pullback state riêng của shadow.
3. Đánh giá Long và Short bằng cùng bias, regime, quality, chop và curl của preset đang test.
4. Ghi một event khi signal chuyển từ false sang true; các nến signal tiếp tục true chỉ tăng `repeatBars`, không tạo event mới.
5. Với mỗi event, lưu giá entry giả định theo bid/ask, InitialSL theo cùng swing logic và risk distance `1R`; tuyệt đối không tính lot hoặc gửi order.
6. Theo dõi first-hit `+1R/-1R`, MFE_R, MAE_R và forward return đến hết 48 nến. Cho phép nhiều event shadow chồng nhau vì chúng chỉ là quan sát.

CSV `Mentor_RSI_MTF_shadow_signals.csv` cần có tối thiểu:

```text
event_id,setup_id,time,side,entry_price,initial_sl,risk_distance,
live_position_state,live_position_side,conflict_type,repeat_bars,
long_valid,short_valid,long_reject,short_reject,
d1_rsi,d1_ema,d1_wma,h4_rsi,h4_ema,h4_wma,
h1_rsi,h1_ema,h1_wma,entry_rsi,entry_ema,entry_wma,
d1_regime_score,h4_regime_score,composite_regime_score,
hit_1r,hit_minus_1r,first_hit,mfe_r,mae_r,
return_6,return_12,return_24,return_48,completed
```

`conflict_type` dùng đúng các nhãn:

- `FLAT_LONG_ONLY`, `FLAT_SHORT_ONLY`, `FLAT_BOTH`.
- `OPEN_SAME_SIDE`, `OPEN_OPPOSITE_SIDE`.

Preset audit:

- V65: V26 + `SHADOW_AUDIT_EVENTS`.
- V66: V63 + `SHADOW_AUDIT_EVENTS`.

V65/V66 chỉ là preset diagnostic; report trading của chúng phải khớp preset nền tương ứng. Không tối ưu shadow parameters.

### Cổng kiểm tra trước khi nghiên cứu priority

- Compile `0 errors, 0 warnings`.
- Chạy smoke một tháng và xác nhận CSV có event hoàn tất, không có event trùng liên tiếp do signal giữ true.
- Chạy V65/V66 trên 2023, 2024, 2025 và 2026-01-01 đến 2026-07-01 bằng real ticks.
- Audit OFF và ON phải có cùng Total Trades, Net Profit, PF, DD, Long/Short và DIAG pyramid; sai khác bất kỳ nghĩa là shadow engine đã làm nhiễu live logic và phải sửa trước.
- Không dùng Development 2019-2022 để chọn priority vì máy hiện tại chỉ có `0% real ticks` cho đoạn này.
- Report rỗng có Expert/Symbol trống, `M0/1970`, bars/ticks bằng 0, thiếu `Test passed` hoặc thiếu `DIAG_SUMMARY source=OnTester` phải bị loại.

### Thiết kế V67-V70: chỉ tạo sau khi V65/V66 có đủ mẫu

Chỉ tạo các preset execution dưới đây nếu mỗi nhóm conflict quan trọng có ít nhất 50 event hoàn tất và shadow outcome dương, không phụ thuộc một năm:

- V67: control `LONG_FIRST`, hành vi hiện tại.
- V68: `SHORT_FIRST`, chỉ thay thứ tự khi đang flat và cả hai signal hợp lệ cùng nến.
- V69: `REGIME_PRIORITY`; composite `>= +4` chọn Long, `<= -4` chọn Short, neutral giữ Long-first. Không đóng/reverse vị thế đang mở.
- V70: `CONFLICT_SKIP`; khi flat và cả hai signal cùng hợp lệ thì không mở lệnh ở nến đó.

Không triển khai cơ chế reverse/defer đối với `OPEN_OPPOSITE_SIDE` trong V67-V70. Trước hết chỉ so sánh priority ở trạng thái flat để giữ blast radius nhỏ và không làm đổi exit/risk.

Điều kiện để một priority candidate được giữ:

- Validation PF `>= 1.15`, OOS PF `>= 1.10`.
- Equity DD `<= 8%`.
- Long PF và Short PF tổng hợp đều `>= 1.05`; chênh lệch không quá `0.25`.
- Trades tối thiểu `250` mỗi giai đoạn tổng và không dưới `75%` preset nền.
- Largest/Gross `< 5%`, Top-3/Gross `< 12%`.
- Không có năm đầy đủ PF dưới `0.95`.
- `stopModifyFail=0`, `postFillViolation=0`.

### Dữ liệu Codex Windows cần trả lại

- File `.mq5` đã compile và các preset V65/V66; chỉ tạo V67-V70 sau khi audit qua cổng.
- Report HTML, `summary.json`, Journal có toàn bộ `DIAG_SUMMARY source=OnTester`.
- CSV shadow signal của từng fold.
- Bảng tổng hợp theo `side`, `conflict_type`, năm và preset: số event, hit-rate `+1R` trước `-1R`, median MFE_R/MAE_R, mean/median return 6/12/24/48.
- Kết luận riêng cho `FLAT_BOTH` và `OPEN_OPPOSITE_SIDE`; không gộp hai nhóm thành một PF chung.

### Không được làm trong vòng này

- Không thay V26 bằng V63.
- Không đổi risk, lot, SL, TP1/TP2, trailing hoặc pyramiding.
- Không thêm BL, Volume, VWAP hoặc Trap.
- Không optimize đồng thời RSI arm, regime threshold và priority.
- Không dùng report invalid hoặc generated ticks 2019-2022 để tuyên bố OOS edge.
- Không coi shadow forward return là lợi nhuận thực thi; nó chỉ dùng để quyết định có đáng tạo preset priority hay không.

---

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

## Vòng cải thiện chất lượng tín hiệu V29-V40

Mục tiêu vòng này là nâng Long PF và PF tổng thể mà vẫn giữ lõi RSI MTF, không thêm BL, Volume, VWAP hoặc Trap. EA được bổ sung các bộ lọc chất lượng tùy chọn, mặc định tắt để preset cũ giữ nguyên hành vi:

- `UseLongQualityFilter`, `LongRequireD1OrH4Bull`, `LongRequireH4Bull`, `LongEntryRSIMax`, `LongH4RSIMin`.
- `UseShortQualityFilter`, `ShortRequireD1OrH4Bear`, `ShortRequireH4Bear`, `ShortEntryRSIMin`, `ShortH4RSIMax`.
- Diagnostic thêm `longQuality` và `shortQuality` trong `DIAG_SUMMARY rejects`.
- Đã bỏ log spam `PYRAMID skip add... raw_lot_below_min_lot`; EA vẫn đếm `skipMinLot` nhưng không in lặp theo tick. Việc này giúp Strategy Tester chạy ổn hơn và giảm nhiễu journal/live.

Nhánh long-quality:

| Preset | Thay đổi chính | Development PF | Validation PF | OOS PF | Long PF OOS | Kết luận |
|---|---|---:|---:|---:|---:|---|
| V29 | Long phải có D1 hoặc H4 bullish | `1.15` | `1.07` | chưa chạy | chưa chạy | Không thắng V26 validation |
| V30 | V29 + không chase long khi RSI entry `> 68` | `1.17` | `1.05` | `1.10` | `1.04` | Cải thiện Long PF/OOS, nhưng chưa thay V26 vì validation yếu hơn |

So với V26, V30 cải thiện rõ Pseudo-OOS 2025-01-01 đến 2026-07-01: Net Profit `+279.07` so với `+106.31`, PF `1.10` so với `1.04`, Equity DD `5.15%` so với `5.78%`, Long PF `1.04` so với `0.95`. Tuy vậy trên Validation 2023-2024, V30 chỉ đạt PF `1.05`, thấp hơn V26 PF `1.11`; nguyên nhân chính là short side giảm còn Short PF `0.84`. Vì vậy V30 được giữ làm candidate nghiên cứu long-quality, chưa thay baseline V26.

Nhánh short-quality filter V33-V36 bị loại trên Development. Các điều kiện short kiểu `ShortRequireD1OrH4Bear`, `ShortRequireH4Bear` hoặc `ShortEntryRSIMin=35` không cải thiện tổng thể: PF chỉ nằm trong vùng `1.07` đến `1.13`, có preset DD lên `12.46%`, và không tốt hơn V30/V26.

Nhánh chỉnh RSI core của short bằng `PullbackShortLevel`:

| Preset | Thay đổi chính | Development PF | Development DD | Validation PF | OOS PF | Kết luận |
|---|---|---:|---:|---:|---:|---|
| V37 | `PullbackShortLevel=55` | `1.16` | `5.90%` | chưa chạy | chưa chạy | Không vượt V30 development |
| V38 | `ShortArmLevel=65`, `PullbackShortLevel=55` | `1.16` | `5.83%` | chưa chạy | chưa chạy | Gần V37, không đủ tốt |
| V39 | `PullbackShortLevel=60` | `1.23` | `6.34%` | `0.99` | chưa chạy | Overfit development, validation âm |
| V40 | `ShortArmLevel=65`, `PullbackShortLevel=60` | `1.25` | `5.92%` | `1.06` | `0.90` | Overfit, OOS âm |

Kết luận vòng V29-V40:

- V26 vẫn là baseline chính thức vì ổn định hơn qua Development, Validation và OOS.
- V30 là hướng tín hiệu đáng giữ lại cho vòng sau vì nâng Long PF và OOS, nhưng cần xử lý short side trước khi thay baseline.
- V39/V40 không được dùng dù development đẹp, vì validation/OOS cho thấy overfit.
- Vòng tiếp theo nên ưu tiên cải thiện exit/trailing hoặc điều kiện thoát riêng cho short trong giai đoạn thị trường bullish, thay vì thêm filter bias cứng.

## Vòng V41-V48: directional exit profile

Mục tiêu vòng này là tách exit/trailing theo chiều lệnh để long có thêm không gian giữ runner, còn short được phòng thủ sớm hơn khi RSI đảo chiều. Vòng này vẫn giữ nguyên lõi RSI MTF, bias core, risk engine, pyramiding risk và entry core; không thêm BL, Volume, VWAP hoặc Trap.

EA được bổ sung các input tùy chọn, mặc định tắt để preset cũ giữ nguyên hành vi:

- `UseDirectionalExitProfile`.
- `LongTP1_R`, `ShortTP1_R`.
- `LongBreakEvenTriggerR`, `ShortBreakEvenTriggerR`.
- `LongStartTrailingAfterR`, `ShortStartTrailingAfterR`.
- `LongTrailATRMultiplier`, `ShortTrailATRMultiplier`.
- `LongTP2RSILevel`, `ShortTP2RSILevel`.
- `LongH4ExitRSILevel`, `ShortH4ExitRSILevel`.
- `UseShortInvalidationExit`, `ShortInvalidationRSILevel`, `ShortInvalidationMaxR`.

Short invalidation chỉ áp dụng cho short, trước TP1, khi R hiện tại không lớn hơn `ShortInvalidationMaxR`, RSI entry cross lên EMA9 và RSI vượt `ShortInvalidationRSILevel`. Diagnostic được tách thêm thành `DIAG_SUMMARY exitProfile`, `DIAG_SUMMARY exitProfileLong`, `DIAG_SUMMARY exitProfileShort`, gồm số lần `tp1`, `tp2`, `h4`, `invalid` và `trail` theo từng chiều lệnh.

Preset mới:

| Preset | Nền | Thay đổi chính |
|---|---|---|
| V41 | V30 | Short defensive A: `ShortTP1_R=0.8`, `ShortBreakEvenTriggerR=0.8`, `ShortStartTrailingAfterR=1.5`, `ShortTrailATRMultiplier=2.6` |
| V42 | V30 | Short defensive B: `ShortTP1_R=1.0`, `ShortBreakEvenTriggerR=0.8`, `ShortStartTrailingAfterR=1.3`, `ShortTrailATRMultiplier=2.4` |
| V43 | V30 | Giống V41, thêm `UseShortInvalidationExit=true` |
| V44 | V30 | Long runner: `LongStartTrailingAfterR=2.5`, `LongTrailATRMultiplier=3.6` |
| V45 | V30 | Kết hợp V41 và V44 |
| V46 | V26 | Giống V41 nhưng nền là V26 |
| V47 | V26 | Giống V43 nhưng nền là V26 |
| V48 | V26 | Giống V45 nhưng nền là V26 |

Compile sau khi triển khai: `0 errors, 0 warnings`.

Kết quả Development 2019-01-01 đến 2022-12-31, deposit 5,000 USD:

| Preset | Net Profit | Profit Factor | Expected Payoff | Equity DD | Trades | Long PF | Short PF | Largest/Gross | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| V41 | `+537.87` | `1.26` | `1.57` | `5.06%` | `342` | `1.26` | `1.27` | `3.43%` | Qua Development |
| V42 | `+548.38` | `1.27` | `1.66` | `5.31%` | `331` | `1.27` | `1.27` | `3.41%` | Qua Development |
| V43 | `+378.61` | `1.15` | `0.84` | `7.96%` | `453` | `1.20` | `1.11` | `3.54%` | Qua ngưỡng tối thiểu nhưng yếu hơn |
| V44 | `+335.90` | `1.16` | `1.06` | `6.48%` | `317` | `1.04` | `1.24` | `4.06%` | Qua ngưỡng tối thiểu |
| V45 | `+519.13` | `1.25` | `1.52` | `4.96%` | `342` | `1.21` | `1.28` | `3.29%` | Qua Development |
| V46 | `+304.36` | `1.14` | `0.87` | `6.90%` | `351` | `0.99` | `1.29` | chưa ghi | Loại do PF và Long PF |
| V47 | `+202.05` | `1.08` | `0.44` | `9.61%` | `458` | `1.03` | `1.13` | chưa ghi | Loại do PF/DD |
| V48 | `+255.26` | `1.12` | `0.73` | `6.94%` | `349` | `0.96` | `1.28` | chưa ghi | Loại do PF và Long PF |

Kết quả Validation 2023-01-01 đến 2024-12-31, deposit 5,000 USD cho các preset đã qua Development:

| Preset | Net Profit | Profit Factor | Expected Payoff | Equity DD | Trades | Long PF | Short PF | Largest/Gross | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| V41 | `-157.03` | `0.95` | `-0.34` | `10.68%` | `466` | `1.38` | `0.75` | `2.78%` | Loại |
| V42 | `-303.68` | `0.90` | `-0.66` | `10.83%` | `458` | `1.43` | `0.67` | `2.83%` | Loại |
| V43 | `-200.95` | `0.94` | `-0.32` | `10.38%` | `631` | `1.35` | `0.75` | `2.33%` | Loại |
| V44 | `+53.41` | `1.02` | `0.13` | `8.25%` | `405` | `1.49` | `0.81` | `3.15%` | Loại |
| V45 | `-306.21` | `0.90` | `-0.66` | `10.80%` | `463` | `1.34` | `0.70` | `2.96%` | Loại |

Không chạy OOS cho V41-V48 vì không preset nào đạt cổng Validation `PF > 1.11`, `Equity DD <= 8%` và `Short PF >= 0.95`.

Kết luận vòng V41-V48:

- V41/V42/V45 có Development đẹp nhưng fail Validation rõ rệt, nguyên nhân chính là short side: Short PF chỉ còn `0.67` đến `0.75`.
- V43 đóng short invalidation `140` lần trên Validation nhưng Short PF vẫn chỉ `0.75`; điều này cho thấy thoát sớm bằng RSI cross lên EMA9 chưa đủ để sửa short trong giai đoạn 2023-2024.
- V44 cải thiện Long PF Validation lên `1.49`, nhưng tổng PF chỉ `1.02` vì Short PF còn `0.81`. Long runner là ý tưởng có tín hiệu, nhưng không được dùng độc lập khi short chưa ổn.
- V26 tiếp tục là baseline chính thức. V30 vẫn là candidate nghiên cứu vì cải thiện Long PF/OOS, nhưng directional exit V41-V48 chưa đủ điều kiện thay thế.
- Vòng tiếp theo không nên tiếp tục siết trailing short đơn thuần. Cần nghiên cứu một lớp nhận diện regime hoặc điều kiện tạm dừng short trong thị trường bullish, nhưng vẫn chỉ dùng RSI MTF/ATR/price action đơn giản để tránh lệch khỏi phạm vi hệ thống.

## Vòng V49-V52: xác minh form quạt RSI

Mục tiêu của vòng này là kiểm chứng độc lập edge của ba điểm entry trong form quạt RSI, trước khi dùng chúng làm các tầng pyramid. V26 vẫn là baseline; không thay đổi `RiskPerTradePct`, SL theo swing, bias `HTF_VETO`, chop filter, trailing hoặc risk của pyramid.

EA có thêm `EntryMode=RSI_FAN_STRUCTURE`. Form long chỉ được xác nhận từ nến `EntryTF` đã đóng theo chuỗi sau:

1. RSI cắt xuống WMA45-RSI, sau đó EMA9-RSI cắt xuống WMA45-RSI trong `FanOriginCrossWindowBars`; khoảng cách cực đại của ba đường tại origin không quá `FanOriginMaxSpread`.
2. Ba đường phải mở rộng tối thiểu `FanMinExpansion` RSI points.
3. RSI cắt lên EMA9 lần đầu, quay xuống dưới EMA9, rồi tạo đáy RSI cao hơn đáy trước tối thiểu `FanMinHigherLowRSI`.
4. RSI cắt lên EMA9 lần hai là Entry 1. Sau Entry 1, RSI vượt mức RSI của Entry 1 và nằm giữa EMA9/WMA45 là Entry 2. RSI cắt lên WMA45 là Entry 3. Nếu RSI cắt thẳng WMA45 trước khi hoàn thành nhịp hồi, `FanAllowDirectWMAEntry=true` ghi nhận đó là Entry 3 mạnh.

Form short là ảnh gương: RSI cắt lên WMA45 trước, EMA9 cắt lên WMA45 sau, rồi tạo lower-high RSI; các điểm Entry 1/2/3 lần lượt là RSI cắt xuống EMA9 lần hai, đi xuống giữa EMA9/WMA45 sau khi vượt vị trí Entry 1, và cắt xuống WMA45.

Mỗi form chỉ cho phép một base trade. `FanEntrySelection` dùng để kiểm chứng:

- `FAN_FIRST_VALID`: mở ở điểm hợp lệ đầu tiên trong E1/E2/E3; đây là cấu hình vận hành sau khi đã có kết quả.
- `FAN_ENTRY1_ONLY`, `FAN_ENTRY2_ONLY`, `FAN_ENTRY3_ONLY`: chỉ mở tại điểm tương ứng để đo edge riêng. Các điểm không được chọn không làm phát sinh lệnh và form tiếp tục đến điểm kế tiếp.

Tín hiệu được tiêu thụ sau điểm entry được chọn, kể cả khi risk engine skip do lot tối thiểu; vì vậy một form không thể phát sinh base trade thứ hai. Pyramiding chỉ hoạt động sau base trade có lời theo cơ chế V26 đã kiểm nghiệm.

`DIAG_SUMMARY` có thêm:

- `fan`: số origin long/short, form hết hạn và form invalid.
- `fanLong`, `fanShort`: số tín hiệu E1/E2/E3 và số lệnh đã mở theo từng điểm.
- `fanParams`: các tham số hình học của form để đối chiếu preset.

Preset nghiên cứu trên nền V26, BTCUSD H1, deposit 5,000 USD:

| Preset | `FanEntrySelection` | Mục đích |
|---|---|---|
| V49 | `FAN_FIRST_VALID` | Đo form quạt như một entry mode vận hành |
| V50 | `FAN_ENTRY1_ONLY` | Đo cú higher-low và RSI recross EMA9 |
| V51 | `FAN_ENTRY2_ONLY` | Đo continuation giữa EMA9/WMA45 |
| V52 | `FAN_ENTRY3_ONLY` | Đo breakout/cross WMA45 |

Thứ tự test chống overfit:

1. Development: 2019-01-01 đến 2022-12-31. Chỉ đưa preset qua Validation nếu có tối thiểu 80 trades, PF >= 1.12, Expected Payoff dương, Equity DD <= 9%, và không có một chiều Long/Short PF dưới 0.95.
2. Validation: 2023-01-01 đến 2024-12-31. Preset cần PF >= 1.08, DD <= 9%, Long PF và Short PF >= 0.95.
3. Pseudo-OOS: 2025-01-01 đến 2026-07-01. Chỉ xem xét thay V26 nếu PF >= 1.04, DD <= 8%, largest profit contribution < 5% gross profit và không thua V26 rõ rệt ở một chiều giao dịch.
4. Chỉ sau khi một điểm entry qua cả ba giai đoạn mới thiết kế tầng pyramid riêng cho chính điểm đó; không tối ưu đồng thời ngưỡng form, exit và pyramid trong cùng một vòng.

Kết quả Development đầu tiên, 2019-01-01 đến 2022-12-31, BTCUSD H1, deposit 5,000 USD:

| Preset | Chọn entry | Net Profit | PF | Expected Payoff | Equity DD | Trades | Long PF | Short PF | Kết luận |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| V49 | `FIRST_VALID` | `-30.99` | `0.79` | `-1.41` | `2.56%` | `22` | `1.85` | `0.59` | Loại |
| V50 | `ENTRY1_ONLY` | `-24.56` | `0.00` | `-24.56` | `0.58%` | `1` | `0.00` | không có mẫu | Loại: mẫu quá nhỏ |
| V51 | `ENTRY2_ONLY` | `0.00` | `0.00` | `0.00` | `0.00%` | `0` | không có mẫu | không có mẫu | Loại: không có lệnh |
| V52 | `ENTRY3_ONLY` | `-6.44` | `0.95` | `-0.31` | `2.15%` | `21` | chưa đủ mẫu | `0.59` | Loại |

`DIAG_SUMMARY fan` xác nhận state machine hoạt động và có 36 origin long, 47 origin short. Tuy nhiên cấu hình hình học ban đầu tạo rất ít Entry 1/2: V50 chỉ mở 1 Entry 1, V51 không mở Entry 2; E3 chiếm gần toàn bộ lệnh và short E3 có PF thấp. Không preset nào đạt cổng Development, vì vậy không chạy Validation/OOS và tuyệt đối không đưa form quạt vào pyramid.

Vòng kế tiếp, nếu tiếp tục nghiên cứu form này, phải là vòng chẩn đoán cấu trúc riêng: giữ nguyên exit/risk/pyramid, chỉ đánh giá số mẫu và chất lượng của origin, higher-low/lower-high và E3 trên H1/M15 trước khi nới một tham số duy nhất. Không dùng kết quả V49-V52 để chỉnh đồng thời nhiều ngưỡng.

## Lưu ý quan trọng

Với BTCUSD và tài khoản 1,000 USD, broker có thể bắt lot tối thiểu 0.01. Nếu risk 0.5% quá nhỏ, bot sẽ skip nhiều lệnh. Để test đúng risk engine, hãy so sánh:

- Tăng initial deposit trong tester.
- Hoặc tăng `RiskPerTradePct` tạm thời để kiểm tra logic entry/exit.
- Hoặc dùng symbol/account có lot step nhỏ hơn.

## Vòng V53-V56: nhánh “lò xo dưới WMA” cho RSI fan

Vòng này kiểm tra giả thuyết: sau origin của form quạt, RSI ở phía nén của WMA45-RSI càng lâu thì cú hồi E2/E3 có thể đáng quan sát hơn. Đây chỉ là giả thuyết xếp hạng tín hiệu; tuyệt đối không được hiểu là lý do tăng lot, tăng `RiskPerTradePct`, nới SL hoặc tăng số tầng pyramid.

V26, MTF bias, SL theo swing, partial exit, trailing và risk của pyramid được giữ nguyên. EA có thêm các input, mặc định tắt để các preset cũ giữ nguyên hành vi:

- `UseFanSpringFallback=false`.
- `FanSpringEqualLowTolerance=0.5`.
- `FanSpringMinBelowWMABars=8`.
- `FanSpringFullBelowWMABars=48`.
- `FanSpringMinCompressionRatio=0.0`.
- `FanSignalFamily=FAN_SIGNAL_ALL` hoặc `FAN_SIGNAL_SPRING_ONLY`.

Khi fallback bật, form không còn bị reset chỉ vì một lần RSI hồi qua EMA9 rồi quay xuống nhưng chưa tạo higher-low/lower-high. EA lưu đáy RSI trước đó và tiếp tục theo dõi các đáy kế tiếp cho đến khi form hết `FanMaxAgeBars`, hoàn thành hoặc xuất hiện origin chiều đối nghịch. Entry 1 chuẩn vẫn yêu cầu đáy mới cao hơn đáy trước ít nhất `FanMinHigherLowRSI` với long; short đối xứng là lower-high.

`BelowWMABars` là số nến `EntryTF` đã đóng ở phía nén kể từ origin: long khi `RSI <= WMA45-RSI`, short khi `RSI >= WMA45-RSI`. Tỷ lệ nén được tính:

```text
CompressionRatio = clamp((BelowWMABars - FanSpringMinBelowWMABars)
                         / (FanSpringFullBelowWMABars - FanSpringMinBelowWMABars), 0, 1)
```

Khi đáy mới bằng hoặc thấp hơn đáy trước trong dung sai `FanSpringEqualLowTolerance`, đồng thời đủ `FanSpringMinBelowWMABars`, form được đánh dấu `springEligible`. Nếu đạt ngưỡng `FanSpringMinCompressionRatio`:

- `SPRING_E2`: RSI vừa cắt EMA9 theo hướng entry nhưng vẫn ở giữa EMA9 và WMA45.
- `SPRING_E3`: RSI cắt WMA45 theo hướng entry.

Mỗi form vẫn chỉ có một base trade. Comment lệnh có dạng `RSI_MTF_LONG_FAN_SPRING_E2_C0` hoặc `RSI_MTF_SHORT_FAN_SPRING_E3_C2`. Diagnostic thêm `fanSpring`, `fanSpringLong`, `fanSpringShort` và các dòng bucket C0–C3; các dòng này đếm form eligible, tín hiệu E2/E3, lệnh mở và số lần spring signal bị chặn bởi bias/chop/curl.

Preset kiểm chứng trên nền V26:

| Preset | Family | Điểm entry | `FanSpringMinCompressionRatio` |
|---|---|---|---:|
| V53 | `SPRING_ONLY` | E2 | `0.00` |
| V54 | `SPRING_ONLY` | E2 | `0.25` |
| V55 | `SPRING_ONLY` | E3 | `0.00` |
| V56 | `SPRING_ONLY` | E3 | `0.25` |

Điều kiện qua Development là ít nhất 40 report trades, PF >= 1.12, Expected Payoff dương, Equity DD <= 9%, Long PF và Short PF >= 0.95. Chỉ preset qua cổng này mới được tạo V57 (`ALL`, `FIRST_VALID`, ưu tiên E1 chuẩn rồi Spring E2 rồi Spring E3), sau đó mới được chạy Validation 2023-2024 và Pseudo-OOS 2025-2026.

Kết quả Development đã chạy bằng MT5, BTCUSD H1, deposit 5,000 USD, 2019-01-01 đến 2022-12-31:

| Preset | Net Profit | PF | Expected Payoff | Equity DD | Report trades | Long PF | Short PF | Largest/Gross | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| V53 | `+6.25` | `57.82` | `+3.13` | `0.28%` | `2` | `57.82` | không có mẫu | `100%` | Loại: chỉ 1 base position, PF không có ý nghĩa thống kê |
| V54 | `0.00` | `0.00` | `0.00` | `0.00%` | `0` | không có mẫu | không có mẫu | `0%` | Loại: không có lệnh |
| V55 | `0.00` | `0.00` | `0.00` | `0.00%` | `0` | không có mẫu | không có mẫu | `0%` | Loại: không có lệnh |
| V56 | `0.00` | `0.00` | `0.00` | `0.00%` | `0` | không có mẫu | không có mẫu | `0%` | Loại: không có lệnh |

`DIAG_SUMMARY fanSpring` cho thấy implementation có phát hiện đúng form, nhưng mẫu không đủ để có edge H1:

- V53: eligible long `5`, short `1`; Spring E2 signal long `5`, short `1`; chỉ một long C0 vượt qua gate và mở base position. Bốn long và một short bị `HTF_VETO` chặn.
- V54: eligible long `5`, short `1`; chỉ có một Spring E2 và một Spring E3 ở bucket C1, cả hai bị bias chặn hoặc không đúng entry selection; không có lệnh mở.
- V55: không có Spring E3 signal ở ngưỡng C0; do đó không có lệnh.
- V56: có một Spring E3 C1 phía long, nhưng bị bias chặn; không có lệnh.

Kết luận vòng V53-V56: nhánh “lò xo dưới WMA” H1 không đạt mẫu tối thiểu và không chứng minh được edge độc lập trên Development. Không tạo V57, không chạy Validation/OOS và không đưa nhánh này vào pyramid hoặc M15 trong vòng hiện tại. V26 tiếp tục là baseline; nhánh Spring được gỡ khỏi source trực tiếp trong đợt dọn sau đó.

## Xác nhận V26 và dọn source trực tiếp

Đã chạy lại V26 bằng preset `26_v23_add1_trigger_2p25_lock_0p75.set` (tên file lịch sử, nhưng tham số đúng V26: `Add1TriggerR=2.25`, `Add1LockFloorR=0.75`) trên BTCUSD H1, deposit 5,000 USD, 2019-01-01 đến 2022-12-31. Kết quả khớp với baseline Development đã ghi trước đó:

| Net Profit | PF | Expected Payoff | Equity DD | Report trades | Long PF | Short PF | Largest/Gross |
|---:|---:|---:|---:|---:|---:|---:|---:|
| `+191.44` | `1.09` | `+0.59` | `8.10%` | `324` | `0.91` | `1.26` | `3.84%` |

Diagnostic của lần xác nhận: `241` base cycles, `7` Add1, `0` Add2, `stopModifyFail=0`, `postFillViolation=0`. Đây là mốc Development để đối chiếu mọi vòng sau. Report hiện vẫn ghi `0% real ticks`; cần đồng bộ dữ liệu real ticks trước khi dùng kết quả để đánh giá độ bền cuối cùng.

Sau khi V53-V56 bị loại, phần Spring đã được gỡ trực tiếp khỏi `Mentor_RSI_MTF_v1.mq5`: input, state tracker, signal family, comment `FAN_SPRING_*` và `DIAG_SUMMARY fanSpring` đều không còn. RSI fan chuẩn V49-V52 được giữ riêng như một nhánh nghiên cứu cấu trúc, nhưng không phải baseline và không được đưa vào pyramid. Các preset/report V53-V56 chỉ còn là hồ sơ lịch sử, không dùng để chạy lại trên source hiện tại.

## Kiểm tra đồng bộ real-tick history

Đã chạy kiểm tra đồng bộ bằng V26, BTCUSD H1, deposit 5,000 USD, `model=4` (`Every tick based on real ticks`). Full range 2019-01-01 đến 2026-07-01 bị agent MT5 ngắt giữa chừng quanh 2023-06-29, nên report full range bị rỗng và không dùng để đánh giá chiến lược.

Các đoạn nhỏ hơn cho kết quả như sau:

| Giai đoạn | History quality | Kết luận dữ liệu |
|---|---:|---|
| Development 2019-01-01 đến 2022-12-31 | `0% real ticks` | Có bars và test chạy được, nhưng không có real ticks thật trong tester hiện tại |
| Kiểm tra riêng năm 2022 | `0% real ticks` | Xác nhận phần cũ trước 2023 vẫn là generated ticks |
| Validation 2023-01-01 đến 2024-12-31 | `87% real ticks` | Có real ticks phần lớn, đủ tốt hơn hẳn Development cũ |
| OOS 2025-01-01 đến 2026-07-01 | `100% real ticks` | Dữ liệu real ticks đầy đủ |

Hàm ý cho các vòng tối ưu: không so sánh cứng tuyệt đối giữa Development 2019-2022 và Validation/OOS nếu chưa có real ticks cho Development, vì chất lượng mô phỏng khác nhau. Có thể tiếp tục dùng 2019-2022 để nghiên cứu tương đối và lọc ý tưởng thô, nhưng quyết định nâng baseline nên ưu tiên các đoạn có real ticks cao, đặc biệt Validation 2023-2024 và OOS 2025-2026. Nếu cần Development cũng là real ticks, phải tải lịch sử tick BTCUSD thủ công trong MT5 hoặc dùng broker/symbol có dữ liệu tick sâu hơn trước 2023.

## Vòng V58-V64: regime RSI và cân bằng Long/Short

V26 tiếp tục là baseline chính thức và V30 chỉ là candidate long-quality. Vòng này không thay đổi risk, SL theo swing, partial exit, trailing hoặc pyramiding. Mục tiêu là tách edge của từng phía và chặn sớm lệnh ngược regime D1/H4 bằng đúng dữ liệu RSI, EMA9-RSI và WMA45-RSI đang có.

Bộ chạy MT5 được gia cố để không nhận report placeholder hoặc report bị agent ngắt giữa chừng. Một report bị loại nếu Expert/Symbol trống, period là `M0/1970`, bars hoặc ticks bằng 0, sai symbol/period/date range, tester log không có `Test passed`, không có `DIAG_SUMMARY core source=OnTester`, hoặc có lỗi initialization/test. `report_summary.py` đồng thời bổ sung bars/ticks, top-3 chu kỳ lợi nhuận trên gross profit và Long/Short PF theo từng năm. Trên baseline V26 Validation 2023-2024, top-3 chu kỳ thắng chiếm `10.36%` gross profit, vẫn dưới giới hạn `12%`.

EA có thêm `RegimeGateMode`, mặc định `REGIME_GATE_OFF` để preset cũ giữ nguyên hành vi:

- `REGIME_D1_EARLY_VETO`.
- `REGIME_D1_H4_COMPOSITE_VETO`.

Score của mỗi timeframe là tổng bốn thành phần có giá trị `-1`, `0` hoặc `+1`:

```text
sign(RSI - WMA45)
+ sign(EMA9 - WMA45)
+ sign(EMA9 hiện tại - EMA9 trước)
+ sign(WMA45 hiện tại - WMA45 trước)
```

`REGIME_D1_EARLY_VETO` chặn short khi D1 score `>= +2` và chặn long khi D1 score `<= -2`. `REGIME_D1_H4_COMPOSITE_VETO` dùng `CompositeScore = 2 * D1Score + H4Score`; short bị chặn khi composite `>= +4`, long bị chặn khi composite `<= -4`. Gate regime đứng sau bias MTF và trước quality filter, không thay đổi cách tính lot hoặc quản lý lệnh đang mở.

Diagnostic thêm `DIAG_SUMMARY regime`, `regimeLong` và `regimeShort`: số setup Long/Short bị chặn và số lệnh đã mở trong bucket bullish, neutral, bearish. Khi regime gate bật, comment entry có hậu tố `_RG_B`, `_RG_N` hoặc `_RG_S` để truy vết report.

Preset của vòng này:

| Preset | Nền | Mục đích |
|---|---|---|
| V58 | V26 | Long-only, regime off |
| V59 | V26 | Short-only, regime off |
| V60 | V30 | Long-only, regime off |
| V61 | V26 | D1 early veto |
| V62 | V26 | D1/H4 composite veto |
| V63 | V30 | D1 early veto |
| V64 | V30 | D1/H4 composite veto |

Compile sau khi triển khai regime gate: `0 errors, 0 warnings`. Thứ tự test là V58-V60 trước để tách nhiễu chéo do EA chỉ giữ một base position, sau đó V61-V64. Mỗi preset được chạy riêng theo các fold 2023, 2024, 2025 và 2026-01-01 đến 2026-07-01, rồi chạy tổng Validation 2023-2024 và OOS 2025-2026. Development 2019-2022 chỉ còn là stress test vì tester hiện có `0% real ticks` cho đoạn này.

### Kết quả V58-V64

Report hai năm của V59 và V61 từng bị MT5 agent ngắt giữa chừng. Bộ validator mới đã loại đúng các report này vì Expert/Symbol trống, period `M0 (1970...)`, bars/ticks bằng 0 và không có OnTester summary. Hai preset được rerun theo từng năm trong phiên sạch; tuyệt đối không sử dụng các report rỗng để tính kết quả.

Kết quả chẩn đoán từng phía:

| Preset/giai đoạn | Net Profit | PF | Equity DD | Trades | PF phía được đo | Largest/Gross | Top-3/Gross |
|---|---:|---:|---:|---:|---:|---:|---:|
| V58 Validation 2023-2024 | `+493.51` | `1.29` | `4.07%` | `282` | Long `1.29` | `4.09%` | `11.86%` |
| V58 OOS 2025-2026 | `+106.36` | `1.07` | `4.72%` | `193` | Long `1.07` | `5.31%` | `14.90%` |
| V59 năm 2023 | `-238.60` | `0.79` | `6.97%` | `140` | Short `0.79` | `9.98%` | `25.26%` |
| V59 năm 2024 | `-318.20` | `0.73` | `11.58%` | `125` | Short `0.73` | `9.65%` | `28.09%` |
| V60 Validation 2023-2024 | `+598.84` | `1.47` | `4.01%` | `220` | Long `1.47` | `4.76%` | `14.70%` |
| V60 OOS 2025-2026 | `+146.63` | `1.13` | `3.72%` | `155` | Long `1.13` | `6.58%` | `17.19%` |

V59 chứng minh short độc lập của V26 không có edge trên 2023-2024. Short PF trong EA ghép tốt hơn vì các vị thế long đang chặn nhiều short yếu. Chiều ngược lại cũng xảy ra trên OOS: V58 Long-only có PF `1.07`, trong khi Long PF của V26 ghép chỉ `0.95`; một số vị thế short cũng chặn long có lợi. Vì vậy Long/Short PF trong report ghép không thể được xem là hai hệ thống độc lập.

Kết quả regime candidate:

| Preset/giai đoạn | Net Profit | PF | Equity DD | Trades | Long PF | Short PF | Largest/Gross | Top-3/Gross | Kết luận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| V61 năm 2023 | `+519.82` | `1.43` | `2.87%` | `205` | `1.87` | `1.09` | `5.84%` | `18.34%` | Chưa đạt concentration |
| V61 năm 2024 | `+179.95` | `1.15` | `4.52%` | `181` | `1.51` | `0.91` | `5.87%` | `18.04%` | Loại do Short PF |
| V62 Validation | `+245.17` | `1.09` | `5.32%` | `402` | `1.45` | `0.86` | `2.98%` | `10.42%` | Loại |
| V63 Validation | `+587.11` | `1.23` | `5.90%` | `368` | `1.58` | `1.03` | `2.90%` | `10.16%` | Qua PF tổng, chưa cân bằng |
| V63 OOS | `+312.70` | `1.14` | `6.17%` | `278` | `0.97` | `1.27` | `4.13%` | `11.32%` | Chưa đạt Long PF và PF gap |
| V64 Validation | `+263.90` | `1.10` | `7.75%` | `403` | `1.51` | `0.88` | `2.88%` | `9.36%` | Loại |

V63 là preset tốt nhất của vòng về PF tổng: Validation PF `1.23` và OOS PF `1.14`, DD dưới `6.2%`, trades lần lượt `368` và `278`, concentration đều đạt. Tuy nhiên V63 không qua cổng cân bằng: Validation chênh Long/Short PF khoảng `0.55`; OOS Long PF chỉ `0.97`, Short PF `1.27`; riêng 2025 Long PF theo chu kỳ chỉ khoảng `0.84`. Diagnostic V63 ghi nhận Validation chặn `667` setup long và `1,186` setup short; OOS chặn `823` long và `805` short. Risk/pyramid vẫn sạch với `stopModifyFail=0` và `postFillViolation=0`.

Kết luận: không preset V61-V64 nào thay V26. V63 được giữ làm candidate nghiên cứu vì nâng PF tổng và giữ DD/concentration tốt, nhưng chưa dùng làm baseline hoặc live preset. Dữ liệu chỉ ra vòng tiếp theo nên xử lý quyền ưu tiên/xung đột khi Long và Short cạnh tranh một vị thế, hoặc đánh giá shadow signal, thay vì tiếp tục siết thêm cùng một regime threshold. Exit, trailing và risk không nên thay đổi trong bước chẩn đoán này.
