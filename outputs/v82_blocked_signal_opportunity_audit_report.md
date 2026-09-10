# V82 — Báo cáo shadow audit tín hiệu bị chặn và chi phí cơ hội

Ngày chốt báo cáo: 2026-09-10
Base V81/V26: `c22f2cb0dbc4b59198fe6a875fcc894d22ffbc6c`
Branch: `research/v82-blocked-signal-opportunity-audit`

## 1. Kết luận điều hành

V82 hoàn tất dưới dạng audit quan sát độc lập. `BlockedSignalShadowMode` mặc
định `OFF`; audit không reverse, không hedge, không close-on-opposite, không
thêm lot và không sửa stop, runner, partial exit hay pyramiding.

| Giả thuyết | Kết luận |
|---|---|
| LONG active → SHORT blocked | `INSUFFICIENT_EVIDENCE` |
| SHORT active → LONG blocked | `PROMISING_FOR_EXECUTION_EXPERIMENT` |
| LONG active → LONG blocked | `INSUFFICIENT_EVIDENCE` |
| SHORT active → SHORT blocked | `INSUFFICIENT_EVIDENCE` |
| Flat, Long và Short đồng thời | `INSUFFICIENT_SAMPLE` — 0 event |

Kết luận “promising” chỉ cho phép thiết kế một execution experiment riêng sau
này. Nó không cấp quyền bật execution gate, reverse hay tạo V83 trong task này.

## 2. Baseline integrity và regression

V82 được tạo từ đúng SHA V81 ở trên. So sánh source cho thấy các thay đổi
execution không xuất hiện trong `LongSignal`, `ShortSignal`, `OpenTrade`,
`ManageOpenPosition`, sizing, stop, partial exit, trailing hoặc pyramiding.
V82 có state, event array và CSV riêng; callback V82 được chặn ngay khi mode
`OFF`, và không gọi `trade.*`.

Smoke dùng BTCUSD H1, real ticks, 2026-06-01 đến 2026-06-30, deposit 5,000 USD,
leverage 1:10. `V26 control` là preset execution V26 với
`BlockedSignalShadowMode=OFF`; `V82 audit` chỉ bật mode quan sát.

| Chỉ số equality | V26 control | V82 audit |
|---|---:|---:|
| Net profit | 12.88 | 12.88 |
| Profit factor | 1.11 | 1.11 |
| Expected payoff | 0.99 | 0.99 |
| Max equity DD | 97.56 (1.91%) | 97.56 (1.91%) |
| Trades / closed cycles | 13 / 11 | 13 / 11 |
| Long / Short trades | 7 / 6 | 7 / 6 |
| Add1 | 0 | 0 |
| Deal sequence | 24 | 24 |
| Deal/cycle/metric mismatches | 0 | 0 |

`compare_execution_regression.py --require-diagnostics` trả về
`equal=true`, `deal_sequence.available=true`,
`execution_diagnostics.equal=true`. Diagnostics execution giống nhau; chỉ
`blockedSignalShadow` được loại khỏi equality vì đó là telemetry được kỳ vọng
khác giữa OFF và ON. Audit ON tạo 97 event; control OFF tạo 0 event V82.

Full-year reports dưới đây là các lần chạy V82 audit thành công, không phải
PF gate. Các lần chạy đều dùng cùng symbol/timeframe/model và không optimization.

| Kỳ | Net | PF | Expected | Max DD | Trades | Cycles | Long / Short |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | 108.48 | 1.08 | 0.53 | 193.46 (3.86%) | 206 | 131 | 97 / 109 |
| 2024 | 36.73 | 1.03 | 0.18 | 452.80 (8.51%) | 205 | 174 | 106 / 99 |
| 2025 | -18.98 | 0.99 | -0.08 | 308.31 (5.85%) | 229 | 189 | 98 / 131 |
| 2026-H1 | 114.93 | 1.14 | 1.15 | 266.21 (5.00%) | 100 | 80 | 53 / 47 |

## 3. Phạm vi và semantics

- Event chỉ được tạo trên một closed `EntryTF` bar; feature/state signal dùng
  shift 1, không dùng bar 0.
- V82 có setup state độc lập, dùng rising edge của signal hợp lệ và setup
  generation để tránh lặp cùng một cơ hội qua nhiều bar.
- `BLOCKED_OPPOSITE` và `BLOCKED_SAME_SIDE` chỉ được ghi khi đang có managed
  position; khi flat, cặp Long/Short đồng thời ghi một
  `SIMULTANEOUS_CONFLICT`, còn `LONG_ONLY`/`SHORT_ONLY` là control population.
- Hypothetical entry dùng Ask cho Long và Bid cho Short. Initial SL dùng pure
  calculation với cùng swing lookback/buffer của V26; invalid risk không tạo
  outcome hợp lệ.
- Một shadow R là `abs(shadow_entry_price - shadow_initial_sl)`. Forward
  checkpoints cố định ở 6/12/24/48 bar.
- Nếu cùng OHLC bar chạm +1R và -1R mà không có thứ tự tick để phân giải,
  first-hit là `AMBIGUOUS`.
- Active continuation là thay đổi giá trị group kể từ event time, không phải
  total R từ lúc mở lệnh. Group value gồm realized P/L, commission, swap, fee
  và unrealized P/L; partial/pyramid leg được giữ trong snapshot group và
  carry-forward khi group đóng trước horizon.

## 4. Event inventory và data quality

| Event type | Tất cả event | Completed hợp lệ |
|---|---:|---:|
| `BLOCKED_OPPOSITE` | 580 | 579 |
| `BLOCKED_SAME_SIDE` | 2,243 | 2,227 |
| `LONG_ONLY` | 360 | 358 |
| `SHORT_ONLY` | 435 | 434 |
| **Tổng** | **3,618** | **3,598** |

Có 20 event hợp lệ ở cuối kỳ chưa đủ 48 bar nên được đánh dấu incomplete và
loại khỏi resolved metrics. Không có build-invalid event được tính vào outcome.

| Kiểm tra | Kết quả |
|---|---:|
| Schema thiếu trường | 0 |
| Missing event ID | 0 |
| Duplicate event ID | 0 |
| NaN / Inf | 0 |
| Numeric, side, event-type, relation, boolean, time invalid | 0 |
| Risk distance âm hoặc zero/missing | 0 |
| Age âm / completed trước horizon | 0 |
| Horizon lookahead | 0 |
| Missing completed outcome | 0 |
| State-mutation violation quan sát được | 0 |
| Quality gate | **PASS** |

## 5. Opportunity-cost results

Định nghĩa chính:

```text
opportunity_diff_h = shadow_return_h - active_continuation_h
```

Giá trị dương nghĩa là nhánh bị chặn tốt hơn phần giá trị tiếp diễn của active
group. Bảng dưới dùng median trên completed events; `+1R first` là tỷ lệ trên
những event resolve được path first-hit.

| Direction | Fold | n | Median Δ24R | Median Δ48R | Shadow +1R first | Active +1R first |
|---|---|---:|---:|---:|---:|---:|
| LONG → SHORT | Validation 2023–2024 | 151 | -0.5083 | -1.0553 | 34.33% | 100.00% |
| LONG → SHORT | OOS 2025+ | 115 | +0.1547 | +0.2152 | 57.80% | 81.48% |
| SHORT → LONG | Validation 2023–2024 | 224 | +0.0417 | -0.0062 | 49.47% | 77.27% |
| SHORT → LONG | OOS 2025+ | 89 | +0.3021 | +0.2226 | 57.14% | 95.45% |
| LONG → LONG | Validation 2023–2024 | 483 | +0.0328 | +0.1762 | 56.74% | 70.41% |
| LONG → LONG | OOS 2025+ | 450 | +0.0076 | +0.0263 | 53.05% | 68.32% |
| SHORT → SHORT | Validation 2023–2024 | 835 | -0.0558 | -0.0250 | 49.86% | 65.31% |
| SHORT → SHORT | OOS 2025+ | 459 | -0.0192 | +0.0796 | 53.64% | 64.38% |

### 5.1. Phân rã return ở horizon chính

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

### 5.2. Event type

| Event type | Completed | Median Δ24R | Median Δ48R | Shadow +1R first | Active +1R first |
|---|---:|---:|---:|---:|---:|
| `BLOCKED_OPPOSITE` | 579 | +0.0263 | -0.1353 | 48.54% | 90.68% |
| `BLOCKED_SAME_SIDE` | 2,227 | -0.0102 | +0.0434 | 52.71% | 66.85% |
| `LONG_ONLY` | 358 | n/a | n/a | 49.27% | n/a |
| `SHORT_ONLY` | 434 | n/a | n/a | 49.26% | n/a |

## 6. Active maturity và pyramid context

Các bucket này chỉ mô tả; không có threshold mining hay subgroup selection.

| Active R tại event | n | Median Δ24R | Median Δ48R |
|---|---:|---:|---:|
| `< 0` | 871 | -0.0148 | -0.0025 |
| `0–1` | 1,232 | -0.0056 | +0.0565 |
| `1–2` | 542 | -0.0371 | +0.0083 |
| `>= 2` | 161 | +0.0762 | +0.0608 |

| Pyramid state | n | Median Δ24R | Median Δ48R | Shadow +1R first | Active +1R first |
|---|---:|---:|---:|---:|---:|
| `before_add1` | 2,784 | -0.0078 | +0.0350 | 51.85% | 69.44% |
| `after_add1` | 22 | -0.3741 | -0.7414 | 50.00% | 83.33% |

`after_add1` chỉ có 22 event, nên không được dùng làm promotion gate.

## 7. Stability theo năm

Median opportunity difference tại 24 bar:

| Direction | 2023 | 2024 | 2025 | 2026-H1 | Năm dương |
|---|---:|---:|---:|---:|---:|
| LONG → SHORT | -0.0743 | -0.9384 | +0.2229 | -0.2790 | 1/4 |
| SHORT → LONG | -0.0227 | +0.1768 | +0.7087 | +0.1671 | 3/4 |
| LONG → LONG | +0.0596 | +0.0161 | +0.0011 | +0.0189 | 4/4 |
| SHORT → SHORT | -0.1148 | -0.0140 | -0.0413 | +0.0022 | 1/4 |

## 8. Promotion gates

Sample gate là tối thiểu 30 completed event ở Validation và 30 ở OOS.
Materiality là median Δ48R ít nhất +0.20 ở một fold hoặc chênh lệch
`+1R first` ít nhất 8 điểm phần trăm ở một fold. Year-concentration yêu cầu
ít nhất 3/3 năm hoặc hơn có sample đạt chuẩn phải dương.

| Direction | Validation / OOS | Direction | Materiality | Stability | Year concentration | Quyết định |
|---|---:|---|---|---|---|---|
| LONG → SHORT | 151 / 115 | FAIL | PASS | FAIL | FAIL, 1/4 | `INSUFFICIENT_EVIDENCE` |
| SHORT → LONG | 224 / 89 | PASS | PASS | PASS | PASS, 3/4 | `PROMISING_FOR_EXECUTION_EXPERIMENT` |
| LONG → LONG | 483 / 450 | PASS | FAIL | PASS | PASS, 4/4 | `INSUFFICIENT_EVIDENCE` |
| SHORT → SHORT | 835 / 459 | FAIL | FAIL | PASS | FAIL, 1/4 | `INSUFFICIENT_EVIDENCE` |

Tất cả directional hypotheses đều có đủ sample ở Validation/OOS. Chỉ
`SHORT active → LONG blocked` vượt toàn bộ promotion gates; đây vẫn là kết quả
nghiên cứu, không phải thay đổi execution.

## 9. Simultaneous conflicts

Bốn kỳ audit có `SIMULTANEOUS_CONFLICT = 0`. Vì vậy actual-selected LONG so
với blocked SHORT không có sample và không được suy diễn thành edge.

## 10. Kiểm thử và artifacts

- MQL5 compile: `0 errors, 0 warnings` với MetaEditor và bộ Standard Library
  runtime cô lập; log build hiện tại là `outputs/build/v82-official-compile.log`
  trong thư mục build bị ignore.
- Python unit tests: `8/8` pass; `py_compile` cho parser, comparator và tests
  pass.
- Full audit đã chạy thành công 2023, 2024, 2025 và 2026-01-01 đến 2026-07-01
  bằng BTCUSD H1 real ticks, không optimization.
- CSV nguồn và summary xác thực nằm trong thư mục build bị ignore:
  `outputs/build/v82_runs/v82_<year>_blocked_signals.csv`,
  `outputs/build/v82_full_summary.json` và `outputs/build/v82_full_summary.md`.
- Parser kiểm tra fail-closed schema, duplicate, NaN/Inf, relation, boolean,
  time, risk, incomplete outcome và horizon lookahead.
- Preset control/audit được commit tại `outputs/presets/`.

## 11. Ranh giới bàn giao

Đã giữ V26 làm baseline, không merge, không deploy, không reverse và không
implement V83. `SHORT active → LONG blocked` chỉ là ứng viên cho một PRD
execution experiment riêng; không có execution gate nào được bật trong V82.
