# V82 — Báo cáo audit tín hiệu bị chặn và chi phí cơ hội

Ngày chạy: 2026-09-09
Base V81: `c22f2cb0dbc4b59198fe6a875fcc894d22ffbc6c`
Branch: `research/v82-blocked-signal-opportunity-audit`

## 1. Kết luận điều hành

V82 đã hoàn tất dưới dạng shadow audit độc lập. Không có thay đổi nào đối với
logic vào lệnh, thoát lệnh, reverse, sizing, stop, partial exit hay pyramiding
của V26. Chế độ mới mặc định `OFF`; kết quả `PROMISING_FOR_EXECUTION_EXPERIMENT`
chỉ là kết luận audit cho một hướng, không cấp quyền triển khai V83 hay thay đổi
execution.

| Giả thuyết | Kết luận |
|---|---|
| LONG active → SHORT blocked | `INSUFFICIENT_EVIDENCE` |
| SHORT active → LONG blocked | `PROMISING_FOR_EXECUTION_EXPERIMENT` |
| LONG active → LONG blocked | `INSUFFICIENT_EVIDENCE` |
| SHORT active → SHORT blocked | `INSUFFICIENT_EVIDENCE` |
| Tín hiệu đồng thời khi đang flat | `INSUFFICIENT_SAMPLE` — có 0 event |

Diễn giải: chỉ giả thuyết `SHORT active → LONG blocked` vượt toàn bộ cổng
sample, direction, materiality, stability và year-concentration. Đây là tín
hiệu để mở một execution experiment riêng trong tương lai; V82 dừng ở audit và
không tự động đảo chiều hay thêm entry.

## 2. Phạm vi và nguyên tắc bất biến

- Symbol/timeframe: BTCUSD H1, real ticks, deposit 5,000, leverage 1:10.
- Các kỳ chạy: 2023, 2024, 2025 và 2026-H1.
- `BlockedSignalShadowMode` có giá trị mặc định `OFF`; preset audit chỉ bật
  telemetry, không bật execution gate.
- V82 có state domain, event array và CSV riêng; không dùng lại
  `armedLongBars`/`armedShortBars` hoặc `UpdateArmedState()` của V26/V81.
- Chỉ đánh giá trên EntryTF bar đã đóng: dữ liệu tín hiệu dùng shift 1 và
  không đọc bar 0 cho quyết định shadow.
- Event là rising edge của tín hiệu hợp lệ, gắn với setup generation và event
  identity; các event trùng bị loại.
- Hypothetical entry dùng Ask cho LONG và Bid cho SHORT. Initial SL và risk
  distance dùng đúng quy ước V26 tại closed bar.
- Forward outcomes cố định ở 6/12/24/48 bar. Nếu cùng một OHLC bar chạm cả
  +1R và -1R, first-hit được ghi là `AMBIGUOUS`, không chọn tùy ý.
- Active economics gồm realized P/L, commission, swap, fee và unrealized value
  của cả group position; có hỗ trợ partial/pyramid và group identifier ổn định.

## 3. Regression không can thiệp execution

Mỗi dòng so sánh chạy cùng source và cấu hình V26, chỉ khác
`BlockedSignalShadowMode` OFF/ON. `compare_execution_regression.py` so sánh
report, deal-cycle và execution diagnostics; telemetry V82 được phép khác.

| Kỳ | Net audit/control | PF | Max DD | Trades | Cycles | Long/Short | Kết quả |
|---|---:|---:|---:|---:|---:|---:|---|
| 2023 | +107.80 / +107.80 | 1.08 | 3.86% | 206 | 131 | 97 / 109 | `equal=true`, 0 mismatch |
| 2024 | +36.52 / +36.52 | 1.03 | 8.51% | 205 | 174 | 106 / 99 | `equal=true`, 0 mismatch |
| 2025 | -19.13 / -19.13 | 0.99 | 5.85% | 229 | 189 | 98 / 131 | `equal=true`, 0 mismatch |
| 2026-H1 | +114.82 / +114.82 | 1.14 | 5.00% | 100 | 80 | 53 / 47 | `equal=true`, 0 mismatch |

Smoke test cuối trên 2026-06: OFF và ON đều có Net `+12.86`, PF `1.11`, DD
`1.91%`, 13 trades và 11 cycles. Audit ON tạo 97 V82 events; control OFF tạo
0 event. Regression vẫn `equal=true`, `mismatches=0` và
`execution_diagnostics.equal=true`.

## 4. Inventory và data quality

| Event type | Tất cả event | Completed hợp lệ |
|---|---:|---:|
| `BLOCKED_OPPOSITE` | 580 | 579 |
| `BLOCKED_SAME_SIDE` | 2,243 | 2,227 |
| `LONG_ONLY` | 360 | 358 |
| `SHORT_ONLY` | 435 | 434 |
| **Tổng** | **3,618** | **3,598** |

Có 20 event hợp lệ nhưng chưa đủ 48 bar ở cuối kỳ, được loại khỏi outcome
metrics; không có event build-invalid bị tính nhầm là outcome.

| Kiểm tra chất lượng | Kết quả |
|---|---:|
| Schema thiếu trường | 0 |
| Duplicate event ID | 0 |
| NaN/Inf | 0 |
| Numeric/time/side/event-type không hợp lệ | 0 |
| Risk distance âm hoặc rỗng | 0 |
| Age âm / completed trước horizon | 0 |
| Horizon lookahead | 0 |
| State-mutation violation quan sát được | 0 |
| Quality gate | **PASS** |

## 5. Định nghĩa opportunity cost

Với horizon `h`:

```text
opportunity_diff_h = shadow_return_h - active_continuation_h
```

Trong đó `shadow_return_h` là return R của tín hiệu bị chặn nếu được giả lập
độc lập; `active_continuation_h` là thay đổi giá trị R của active trade group
từ thời điểm event đến horizon. Giá trị dương nghĩa là nhánh bị chặn tốt hơn
phần tiếp diễn của vị thế đang giữ; giá trị âm nghĩa là giữ active trade có
giá trị hơn. Các số dưới đây là median trên completed valid events.

## 6. Kết quả theo hướng và fold

`+1R first` được tính trên các event đã resolve được first-hit; các return và
opportunity difference dùng toàn bộ completed event có giá trị tại horizon.

| Direction | Fold | n | Median Δ24R | Median Δ48R | Shadow +1R first | Active +1R first | Kết luận |
|---|---|---:|---:|---:|---:|---:|---|
| LONG active → SHORT blocked | Validation 2023–2024 | 151 | -0.5083 | -1.0553 | 34.33% | 100.00% | Insufficient |
| LONG active → SHORT blocked | OOS 2025+ | 115 | +0.1547 | +0.2152 | 57.80% | 81.48% | Insufficient |
| SHORT active → LONG blocked | Validation 2023–2024 | 224 | +0.0417 | -0.0062 | 49.47% | 77.27% | Promising |
| SHORT active → LONG blocked | OOS 2025+ | 89 | +0.3021 | +0.2226 | 57.14% | 95.45% | Promising |
| LONG active → LONG blocked | Validation 2023–2024 | 483 | +0.0336 | +0.1767 | 56.74% | 70.41% | Insufficient |
| LONG active → LONG blocked | OOS 2025+ | 450 | +0.0076 | +0.0263 | 53.05% | 68.32% | Insufficient |
| SHORT active → SHORT blocked | Validation 2023–2024 | 835 | -0.0558 | -0.0213 | 49.86% | 65.31% | Insufficient |
| SHORT active → SHORT blocked | OOS 2025+ | 459 | -0.0178 | +0.0796 | 53.64% | 63.91% | Insufficient |

### 6.1. Phân rã return ở horizon chính

| Direction | Fold | Shadow median R24 | Active continuation median R24 | Shadow median R48 | Active continuation median R48 |
|---|---|---:|---:|---:|---:|
| LONG → SHORT | Validation | -0.4553 | +0.0140 | -0.7450 | +0.1215 |
| LONG → SHORT | OOS | -0.0540 | -0.2395 | +0.0824 | -0.3262 |
| SHORT → LONG | Validation | -0.0698 | -0.0924 | -0.1030 | -0.2135 |
| SHORT → LONG | OOS | +0.1610 | -0.3094 | -0.0331 | -0.3770 |
| LONG → LONG | Validation | -0.0186 | -0.1189 | +0.2777 | -0.0667 |
| LONG → LONG | OOS | -0.0055 | -0.1108 | -0.0290 | -0.0897 |
| SHORT → SHORT | Validation | -0.1776 | -0.0704 | -0.1143 | -0.0648 |
| SHORT → SHORT | OOS | -0.1266 | -0.1768 | +0.1456 | -0.2384 |

## 7. Event type, maturity và pyramid context

| Event type | Completed | Median Δ24R | Median Δ48R | Ghi chú |
|---|---:|---:|---:|---|
| `BLOCKED_OPPOSITE` | 579 | +0.0263 | -0.1353 | Hai hướng trái dấu nhau |
| `BLOCKED_SAME_SIDE` | 2,227 | -0.0096 | +0.0434 | Không đạt materiality |
| `LONG_ONLY` | 358 | n/a | n/a | Flat control |
| `SHORT_ONLY` | 434 | n/a | n/a | Flat control |

| Active R tại event | n | Median Δ24R | Median Δ48R |
|---|---:|---:|---:|
| `< 0` | 871 | -0.0148 | -0.0025 |
| `0–1` | 1,232 | -0.0054 | +0.0597 |
| `1–2` | 542 | -0.0345 | +0.0059 |
| `>= 2` | 161 | +0.0767 | +0.0608 |

| Pyramid state | n | Median Δ24R | Median Δ48R | Shadow +1R first | Active +1R first |
|---|---:|---:|---:|---:|---:|
| Trước add1 | 2,784 | -0.0074 | +0.0354 | 51.85% | 69.35% |
| Sau add1 | 22 | -0.3741 | -0.7414 | 50.00% | 83.33% |

Nhóm sau add1 chỉ có 22 event và chỉ mang tính mô tả, không dùng làm cổng
promotion.

## 8. Stability theo năm

Median opportunity difference ở 24 bar:

| Direction | 2023 | 2024 | 2025 | 2026-H1 | Số năm dương |
|---|---:|---:|---:|---:|---:|
| LONG → SHORT | -0.0738 | -0.9384 | +0.2229 | -0.2785 | 1/4 |
| SHORT → LONG | -0.0227 | +0.1768 | +0.7087 | +0.1671 | 3/4 |
| LONG → LONG | +0.0605 | +0.0165 | +0.0011 | +0.0189 | 4/4 |
| SHORT → SHORT | -0.1148 | -0.0140 | -0.0387 | +0.0022 | 1/4 |

## 9. Promotion gates

Tiêu chí sample: tối thiểu 30 completed event ở Validation và 30 ở OOS. Tiêu
chí materiality: median Δ48R đạt ít nhất `+0.20` ở một fold hoặc chênh lệch
`+1R first` đạt ít nhất 8 điểm phần trăm ở một fold. Year-concentration yêu cầu
ít nhất 3/3 năm hoặc hơn có sample đạt chuẩn phải dương.

| Direction | Validation/OOS sample | Direction | Materiality | Stability | Year concentration | Quyết định |
|---|---|---|---|---|---|---|
| LONG → SHORT | 151 / 115 | FAIL | PASS | FAIL | FAIL, 1/4 | `INSUFFICIENT_EVIDENCE` |
| SHORT → LONG | 224 / 89 | PASS | PASS | PASS | PASS, 3/4 | `PROMISING_FOR_EXECUTION_EXPERIMENT` |
| LONG → LONG | 483 / 450 | PASS | FAIL | PASS | PASS, 4/4 | `INSUFFICIENT_EVIDENCE` |
| SHORT → SHORT | 835 / 459 | FAIL | FAIL | PASS | FAIL, 1/4 | `INSUFFICIENT_EVIDENCE` |

Tín hiệu đồng thời có `0` event trong bốn kỳ chạy; so sánh actual-selected
LONG với blocked SHORT vì vậy chưa thể kết luận và được ghi nhận là
`INSUFFICIENT_SAMPLE`.

## 10. Kiểm thử và artifact

- MQL5 compile: `0 errors, 0 warnings`.
- Python unit test: `3/3` pass trong
  `tools/mt5/test_blocked_signal_summary.py`.
- Summary parser chỉ dùng Python standard library, có kiểm tra schema,
  duplicate, NaN/Inf, numeric/time, horizon và incomplete event.
- Full CSV và summary theo từng kỳ nằm trong:
  `backtests/v82_audit_2023/`, `backtests/v82_audit_2024/`,
  `backtests/v82_audit_2025/`, `backtests/v82_audit_2026_h1/`.
- Preset audit và control nằm trong `outputs/presets/`.
- Một lần chạy control 2023 đầu tiên bị validator loại vì MT5 hủy tải history
  và tạo placeholder M0/1970; lần chạy thành công `v82_control_2023_r2` mới là
  dữ liệu dùng để regression.

## 11. Ranh giới bàn giao

Bản này chỉ bổ sung quan sát, CSV, summary và báo cáo. Không merge, không
deploy, không reverse signal, không bật execution gate và không thay đổi V26
baseline. Bất kỳ thử nghiệm execution nào dựa trên hướng `SHORT active → LONG
blocked` phải được thực hiện trong một PRD/branch riêng với gate và regression
riêng.
