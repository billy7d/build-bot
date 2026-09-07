# V81 Standard Deviation Shadow Audit

Ngày chạy: 2026-09-07
Baseline: V26 — `outputs/presets/26_v23_add1_trigger_2p25_lock_0p75.set`
Forward baseline không thay đổi: `outputs/presets/79_v26_forward_demo.set`

## A. Implementation

V81 thêm lớp audit read-only trong `outputs/Mentor_RSI_MTF_v1.mq5` và giữ
`StandardDeviationShadowMode=STDDEV_SHADOW_OFF` mặc định. Preset V81 bật audit
nhưng giữ toàn bộ execution gate mới ở OFF.

Các field được append vào shadow CSV, không rename/xóa field cũ:

- `entry_return_std_20`: population StdDev của 20 log return đóng,
  `ln(Close[t] / Close[t+1])`.
- `entry_return_std_rank`: percentile rank cố định trên 480 quan sát lịch sử
  trước event.
- `entry_price_std_20`, `entry_price_std_100` và
  `entry_price_std_pct_20=StdDev20/SMA20*100`.
- `entry_std_ratio_20_100`, `entry_price_z20`, `entry_price_abs_z20`.
- `entry_rsi_std_20`, `entry_rsi_std_rank`.
- `entry_atr_return_std_ratio=(ATR14/Close)/return_std_20` và rank lịch sử
  `entry_atr_return_std_rank`.

Để tránh lookahead, feature dùng `CopyRates(..., 1, ...)` và
`CopyBuffer(..., 1, ...)`; rank so sánh event hiện tại với các offset lịch sử
`1..480`, loại trừ quan sát hiện tại. Cache được khóa theo thời gian bar.
Khi dữ liệu không hợp lệ, EA ghi empty/`EMPTY_VALUE`, không thay bằng zero.

H2 cũng đã có context cho pyramid shadow:
`add_entry_price_z20`, `add_entry_abs_z20`, `add_return_std_rank`,
`add_atr_return_std_ratio`, `add_atr_return_std_rank`.

Không có thay đổi trong signal, sizing, risk plan, SL/TP, partial exit,
break-even, trailing, pyramid execution, armed state, bias, RSI logic hoặc
market-state gate. Hàm audit trả về trước khi lấy dữ liệu khi mode OFF.

### Protocol tránh overfitting

- Period đã đăng ký trước: return 20, price fast 20, price slow 100, RSI 20,
  rank 480; không chạy grid search/optimizer.
- Bucket cố định: rank `<20`, `20..80`, `>=80`; ratio
  `<0.80`, `0.80..1.25`, `>1.25`; abs-Z `<1`, `1..2`, `>=2`.
- ATR/return-StdDev rank được tính trong EA từ 480 quan sát đóng trước từng
  event, không lấy phân phối gộp từ OOS để định nghĩa bucket.
- Fold cố định: validation 2023–2024; OOS 2025 trở đi.
- Summary luôn tách LONG/SHORT và chỉ đánh dấu bucket đủ diễn giải khi có ít
  nhất 30 events và 20 resolved events. Đây là cờ chất lượng mẫu, không phải
  execution gate.
- Outcome chỉ được dùng hậu nghiệm cho MFE/MAE và forward returns; không được
  dùng để chọn threshold hay thay đổi V26.

## B. Smoke regression

Thiết lập: BTCUSD H1, 2026-06-01 → 2026-06-30, 100% real ticks,
deposit 5,000 USD, leverage 1:10, model real ticks.

| Metric | Control StdDev OFF | V81 audit ON |
|---|---:|---:|
| Net Profit | 12.86 | 12.86 |
| Profit Factor | 1.11 | 1.11 |
| Expected Payoff | 0.99 | 0.99 |
| Equity DD | 97.56 (1.91%) | 97.56 (1.91%) |
| Report trades | 13 | 13 |
| Closed cycles | 11 | 11 |
| Long trades | 7 | 7 |
| Short trades | 6 | 6 |
| Pyramid add1/add2 | 0 / 0 | 0 / 0 |

`compare_execution_regression.py` cho `equal=true`, không có mismatch ở
report metric hoặc closed-cycle identity. 22 dòng execution diagnostics cũng
giống hệt; khác biệt duy nhất có chủ đích là telemetry `stdDevShadow`:
control `events=0`, audit `events=97 complete=97 missing=0 buildFail=0`.

## C. Audit data quality

| Period | History quality | Ticks | Bars | Shadow rows | Completed | Flat-completed |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 75% real ticks | 38,934,614 | 8,736 | 1,002 | 996 | 132 |
| 2024 | 100% real ticks | 84,071,719 | 8,760 | 1,072 | 1,068 | 239 |
| 2025 | 100% real ticks | 150,135,228 | 8,736 | 1,032 | 1,027 | 313 |
| 2026-01-01 → 2026-07-01 | 100% real ticks | 16,847,124 | 4,344 | 512 | 507 | 108 |

Tổng cộng: 3,618 rows, 3,598 completed, 792 flat-completed, 20 incomplete.
Mỗi run có `stdDev events = complete`, `missing=0`, `buildFail=0`.

Quality gate trên cả bốn CSV:

- schema thiếu: 0;
- missing numeric: 0;
- invalid numeric: 0;
- NaN/Infinity: 0;
- StdDev âm: 0;
- rank ngoài `[0,100]`: 0;
- `abs Z < 0`: 0;
- tất cả numeric values finite: true.

Năm 2023 chỉ có 75% real ticks theo report MT5, nên trọng số bằng chứng của
năm này thấp hơn các kỳ còn lại và không được coi là OOS 100% real-tick.

## D. H1 Noise Regime

Phân tích dùng `entry_atr_return_std_rank`, chỉ trên completed `FLAT_*` events,
tách side. `mean24R` và `mean48R` là mean forward return theo R.

| Fold / side | Bucket | n / resolved | +1R first | mean24R | mean48R |
|---|---|---:|---:|---:|---:|
| Validation / LONG | high ≥80 | 25 / 22* | 40.9% | -0.640 | 0.689 |
| Validation / LONG | low <20 | 38 / 26 | 46.2% | -0.131 | 0.546 |
| Validation / LONG | normal | 99 / 78 | 57.7% | 0.158 | 0.341 |
| Validation / SHORT | high ≥80 | 48 / 44 | 43.2% | -0.001 | 0.569 |
| Validation / SHORT | low <20 | 43 / 31 | 54.8% | 0.045 | 0.145 |
| Validation / SHORT | normal | 118 / 88 | 44.3% | -0.231 | -0.273 |
| OOS / LONG | high ≥80 | 33 / 26 | 46.2% | -0.027 | -0.300 |
| OOS / LONG | low <20 | 52 / 38 | 52.6% | 0.032 | 0.277 |
| OOS / LONG | normal | 111 / 84 | 44.0% | 0.042 | -0.064 |
| OOS / SHORT | high ≥80 | 44 / 38 | 42.1% | 0.030 | 0.320 |
| OOS / SHORT | low <20 | 54 / 39 | 64.1% | -0.161 | -0.332 |
| OOS / SHORT | normal | 127 / 99 | 47.5% | 0.197 | 0.233 |

`*` bucket validation LONG/high không đạt sample floor 30 events. High-ratio
noise không cho cùng một dấu hiệu giữa validation và OOS, đặc biệt LONG; vì
vậy H1 chưa đủ bằng chứng để làm veto, risk multiplier hoặc threshold
execution.

## E. H2 Price Extension

Phân tích base signal dùng `entry_price_abs_z20`, cùng fold/side và cùng sample
floor. Kết quả không cho thấy bucket `outside_2sigma` ổn định kém hơn giữa hai
fold:

| Fold / side | inside 1σ (n, mean24R) | between 1–2σ (n, mean24R) | outside ≥2σ (n, mean24R) |
|---|---:|---:|---:|
| Validation / LONG | 26*, -0.711 | 78, 0.075 | 58, 0.125 |
| Validation / SHORT | 51, 0.187 | 110, -0.193 | 48, -0.285 |
| OOS / LONG | 39, -0.188 | 102, 0.145 | 55, -0.035 |
| OOS / SHORT | 45, 0.456 | 129, -0.138 | 51, 0.292 |

`*` validation LONG/inside chỉ có 26 events. Base-signal evidence không ổn
định đủ để chặn Add1 theo Z-score.

Các kỳ trên giữ `PyramidShadowMode=PYRAMID_SHADOW_OFF` và
`ExportPyramidShadowCsv=false`, nên không có Add1 shadow rows để kết luận
trực tiếp cho H2 pyramid. Context Add1 đã được nối vào schema/code để một
vòng audit pyramid riêng có thể đo mà không sửa execution.

## F. RSI compression/expansion

Phân tích dùng `entry_rsi_std_rank`:

| Fold / side | low <20 (n, +1R first) | normal (n, +1R first) | high ≥80 (n, +1R first) |
|---|---:|---:|---:|
| Validation / LONG | 13*, 58.3% | 98, 49.3% | 51, 56.4% |
| Validation / SHORT | 21*, 29.4% | 136, 48.2% | 52, 47.1% |
| OOS / LONG | 21*, 35.0% | 112, 48.3% | 63, 48.7% |
| OOS / SHORT | 27*, 42.3% | 137, 53.1% | 61, 45.9% |

Các bucket low có n dưới 30 ở cả hai fold/side cần dấu `*`. High RSI rank
không duy trì lợi thế nhất quán; chưa đủ bằng chứng cho compression/expansion
filter.

## G. Kết luận

**insufficient evidence**

V81 đạt mục tiêu audit: execution control và audit ON identical trong smoke,
telemetry đầy đủ, dữ liệu không có lookahead theo contract closed-bar, và summary
không dùng optimizer/OOS để chọn bucket. H1 noise, H2 extension và RSI rank đều
chưa có bằng chứng ổn định qua validation → OOS và LONG → SHORT để chuyển thành
execution rule.

Không bật bất kỳ StdDev execution gate nào. V26 tiếp tục là baseline duy nhất;
không merge main, không deploy live và không thay forward demo.
