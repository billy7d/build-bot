# Phase 4 — Thiết kế học tăng tốc cho Trading Agent (v2.1)

Trạng thái: `PROPOSAL v2.1 / DUYỆT CÓ ĐIỀU KIỆN`
Ngày: 2026-10-01 (v2), 2026-10-05 (v2.1)
Phạm vi: nghiên cứu, offline và shadow. Tài liệu này **không** cấp quyền thực thi, không thăng hạng
model, không đưa preset mới vào forward và không chấp thuận giao dịch.

Bất biến giữ nguyên trong toàn bộ Phase 4:

```text
LIVE_TRADING=NO
EXECUTION_AUTHORITY=NONE
AUTO_ACTIVATION=NO
BASELINE_CONTROL=V26
```

## 0. Lịch sử thay đổi

| Phiên bản | Thay đổi |
|---|---|
| v1 | Đề xuất ban đầu: C1 replay engine, C2 dữ liệu đa thị trường, C3 meta-labeling, C4 challenger, C5 agent loop |
| v2 | Tích hợp review của operator và đối chiếu repo: kê khai dữ liệu đã dùng (§2), sửa holdout (§6.1), mốc thời gian chung cho model gộp (§5.3), phạm vi tin cậy của parity theo loại dữ liệu (§5.1), nhãn không phải mẫu độc lập (§5.2), khai báo trước hiệu chỉnh đa phép thử (§6.2), registry bắt đầu từ đầu (§6.3), trạng thái `INCONCLUSIVE`, tách G5 (§7), bảo vệ dữ liệu forward (§6.4), sửa định nghĩa domain theo `EntryTF` |
| v2.1 | Sau khi đọc cơ chế memory/reflection của TauricResearch/TradingAgents (commit `1394a3f`): thêm rò rỉ qua kiến thức sẵn có của LLM (§6.6), thời điểm biết được `known_at_utc` và truy vấn `as_of` cho registry (§6.3), bài học phải là kết quả gộp có thống kê thay vì reflection theo từng mẫu (§5.5), phân loại holdout theo nguồn gốc giả thuyết (§6.1) |

### 0.1 Phạm vi được duyệt ngay

| Hạng mục | Trạng thái |
|---|---|
| 4.0 Chuẩn bị và vận hành collector Phase 3.1 trên máy 1 | Operator ra chỉ thị ngày 2026-10-01; chi tiết trong `docs/trading_agent/phase3/MACHINE1_FORWARD_COLLECTION_HANDOFF_20261001.md` |
| 4A Phát triển offline Python replay engine và parity harness | Được duyệt |
| 4B Kiểm kê dữ liệu (chưa dựng nhãn `core_exit_r`) | Được duyệt |
| Registry, preregistration, khóa split và holdout | Được duyệt, **phải hoạt động trước lần train đầu tiên** |
| Train model 4C, deploy challenger 4D, mở holdout, đưa preset vào forward | **Chưa duyệt**, xét riêng khi có evidence |

---

## 1. Vấn đề

| Nguồn | Số liệu | Ý nghĩa |
|---|---|---|
| `split_manifest.json` Phase 2 | `3618` canonical opportunities BTCUSD H1, từ 2023-01-01 đến 2026-06-30; TRAIN 1002 / VAL 1072 / OOS 1544; 29 feature | Dữ liệu ít |
| `model_validation.md` Phase 2 | ROC-AUC `0.47–0.53`; Brier không tốt hơn unconditional prior | `PREDICTIVE_EDGE_STATUS=NOT_DEMONSTRATED` |
| `agent/phase3/config.py` | `classification_min_resolved=500`; `FORWARD_SAMPLE_COUNT=0` | Cần nhiều tháng forward mới đủ mẫu |
| Chu trình backtest | MT5 Strategy Tester, mỗi preset một lần chạy dài | Thí nghiệm chậm |

Nút thắt là lượng dữ liệu và tốc độ thí nghiệm, không phải độ phức tạp của model. Dùng model phức tạp
hơn trên cùng 3.6k mẫu nhiễu gần như chắc chắn chỉ làm overfit nhanh hơn.

---

## 2. Kê khai dữ liệu đã dùng

Dữ liệu đã tham gia lựa chọn model, feature hoặc preset **không thể** trở thành holdout, kể cả khi được
chuyển ra ngoài repo.

| Domain | Khoảng thời gian | Đã dùng cho | Trạng thái |
|---|---|---|---|
| BTCUSD, `EntryTF=H1` | 2019–2022 | Development/stress V26–V80 (không đủ real ticks) | `USED` |
| BTCUSD, `EntryTF=H1` | 2023-01-01 – 2024-12-31 | Validation V26–V80; Phase 2 TRAIN và VALIDATION | `USED` |
| BTCUSD, `EntryTF=H1` | 2025-01-01 – 2026-07-01 | OOS V26/V63 (chọn V63 làm challenger); Phase 2 OOS (đã xem kết quả); smoke tháng 06/2026 | `USED` |
| BTCUSD, `EntryTF=H1` | 2026-07-01 – nay | Chưa thấy dùng trong repo | `UNVERIFIED_CLEAN`: cần kiểm tra lại evidence local trước khi dùng |
| BTCUSD, `EntryTF=H1` | Từ ngày bắt đầu forward Phase 3.1 | Forward shadow | `FORWARD_RESERVED` |
| ETHUSD, XAUUSD, EURUSD | Toàn bộ lịch sử | Chưa nghiên cứu | `CLEAN` |

Hệ quả:

- **BTCUSD H1 không còn holdout lịch sử sạch.** Xác nhận độc lập cho BTCUSD H1 phải dựa vào dữ liệu
  forward mới (§6.4).
- Các domain chưa được nghiên cứu vẫn còn holdout lịch sử sạch.
- Bảng này được cập nhật mỗi khi một khoảng dữ liệu được dùng. Mỗi lần cập nhật được ghi vào registry (§6.3).

---

## 3. Nguyên tắc thiết kế

1. **Học trên lịch sử, xác nhận trên forward.**
2. **MT5 là trọng tài, không phải phòng thí nghiệm.** Thí nghiệm chạy trên engine Python. Ứng viên cuối
   quay lại MT5.
3. **Thu hẹp câu hỏi.** Model chỉ học cách lọc tín hiệu của engine RSI (meta-labeling), không tự sinh
   chiến lược.
4. **Mọi phép thử đều bị đếm**, cộng dồn qua các vòng.
5. **Có dữ liệu mà agent không được nhìn**: holdout lịch sử của domain sạch và outcome forward.
6. **Tách quyền.** Agent đề xuất kèm bằng chứng. Operator quyết định.
7. **Không đạt ngưỡng chứng minh edge không có nghĩa là đã chứng minh không có edge.** Báo cáo dùng ba
   trạng thái: `EDGE`, `NO_EDGE`, `INCONCLUSIVE`.

---

## 4. Kiến trúc

```text
          ┌──────────────────────────── MÁY 1 (runtime) ────────────────────────────┐
          │ MT5 demo: V26 (preset 83) + V63 (preset 84); account/magic/data-folder riêng│
          │   └─ FILE_COMMON/phase3/opportunities/*.jsonl  (observer V81, closed-bar) │
          │ Collector Phase 3.1 (execution_mode=NONE)                                 │
          │   ├─ Champion bundle (frozen)                                             │
          │   ├─ [4D, chưa duyệt] Challenger bundles ≤2                               │
          │   └─ Outcome resolver (chỉ bar sau event và sau commit)                   │
          │ Export: status/coverage tổng hợp (không có outcome, không có credential)  │
          └────────────────────────────────┬─────────────────────────────────────────┘
                                           │ Git: chỉ health/coverage; outcome theo lịch §6.4
          ┌────────────────────────────────▼──────── MÁY 2 (research/operator) ───────┐
          │ Registry + preregistration + khóa split/holdout (bắt đầu TRƯỚC 4C)         │
          │ C1 Python replay engine ◄── parity gate (phạm vi theo dữ liệu) ── MT5     │
          │ C2 Dataset domain=(symbol, EntryTF) + label manifest                      │
          │ C3 Meta-labeling, walk-forward với mốc thời gian chung                    │
          │ C5 Agent research loop (chỉ bật sau khi công cụ được kiểm chứng)          │
          │ → Evidence pack → OPERATOR                                                │
          └────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Thành phần

### 5.1 C1 — Python replay engine và parity gate

**Phạm vi logic:** indicator RSI(14)/EMA(9)/WMA(45) trên RSI; bias D1/H4/H1; `EntryTF`; entry mode, arm,
tuổi setup, chop filter, regime gate; SL swing + buffer; sizing theo contract spec và **không ép min-lot**;
TP1 partial, BE, TP2 RSI curl, H4 RSI exit, ATR chandelier; pyramiding tối đa 2 add; bất biến một
position/group, xét Long trước Short.

**Parity theo mức và theo loại dữ liệu:**

| Mức | Tiêu chí | Dữ liệu đầu vào bắt buộc |
|---|---|---|
| P1 Indicator | Sai lệch ≤ `1e-6` trên mọi bar | Bar đóng (OHLC) export từ cùng terminal |
| P2 Signal | Cùng tập accepted-entry (timestamp, side, mode); chênh lệch `0` | Bar đóng |
| P3 Order/deal | Cùng chuỗi order/deal; lot khớp volume step; SL/TP khớp tick size | **Tick Bid/Ask** export từ MT5, cùng spread và cùng mô hình execution |
| P4 Report | Net, PF, DD, closed cycles khớp trong sai số làm tròn | Tick như P3 |

Quy định:

- P1–P4 đối chiếu trên **cùng** dữ liệu, cùng cấu hình và cùng giả định execution.
- Báo cáo ghi rõ đoạn nào dùng tick thật và đoạn nào là tick MT5 tự sinh do thiếu dữ liệu.
- Trạng thái tin cậy gắn với phạm vi đã kiểm chứng:
  `(code blob, preset SHA, symbol, broker/server, replay mode, khoảng ngày)`. Ngoài phạm vi đó, engine là
  `NOT_TRUSTED`.
- Replay bằng bar chỉ được dùng cho kết luận cấp P1/P2 (tín hiệu, feature). Kết luận về PnL, exit hoặc
  sizing cần P3/P4.
- Mọi thay đổi `.mq5` bắt buộc chạy lại parity.
- Ứng viên được kiểm tra tích hợp bằng MT5 trên dữ liệu development **trước** khi dùng holdout, để không
  tiêu tốn holdout vì lỗi kỹ thuật.

### 5.2 C2 — Dataset và label manifest

**Domain = (symbol, `EntryTF`).** Timeframe của chart không tạo domain mới vì EA cố định D1/H4/H1 và chỉ
`EntryTF` thay đổi (M15 hoặc H1).

**Universe đợt 1:**

| Domain | Vai trò |
|---|---|
| BTCUSD, H1 | Domain mục tiêu. Chỉ xác nhận bằng forward (§2) |
| ETHUSD, H1 | Domain phụ, có holdout sạch |
| XAUUSD, H1 | Domain phụ, có holdout sạch |
| EURUSD, H1 | Domain phụ, có holdout sạch |

H4/D1 vẫn được tải để tính bias. Thêm mã và `EntryTF=M15` chỉ ở đợt sau, khi pipeline đã chứng minh
chạy đúng và chi phí đã được đo.

**Kiểm kê trước khi gộp domain (bắt buộc):** vì EA được tinh chỉnh cho BTCUSD, mỗi domain phải báo cáo:
số tín hiệu theo năm; tỷ lệ `raw_lot_below_min_lot`; phân phối SL/ATR và spread/R; contract spec
(min-lot, volume step, tick size/value); tỷ lệ tick thật. Domain có tỷ lệ bỏ lệnh hoặc spread bất thường
được ghi `EXCLUDED` kèm lý do, không tự sửa tham số EA để "cứu" domain.

**Provenance:** broker, server, khoảng thời gian, SHA-256 từng file. Dữ liệu trước 2023 không có real
ticks nên chỉ dùng cho P1/P2; nhãn `core_exit_r` ở đoạn đó gắn cờ `BAR_ONLY_LOW_CONFIDENCE`.

**Label manifest (bắt buộc, versioned):**

| Nhãn | Định nghĩa |
|---|---|
| `tb_1r_1r_24` | +1R trước −1R trong 24 bar `EntryTF` |
| `tb_2r_1r_48` | +2R trước −1R trong 48 bar |
| `core_exit_r` | R-multiple theo exit lõi của EA. **Chỉ dựng sau khi P3/P4 PASS** |
| `fwd_ret_{6,12,24,48}` | Forward return chuẩn hóa ATR |
| `mfe_r`, `mae_r` | MFE/MAE theo R |

Manifest phải quy định cách xử lý các trường hợp sau:

- **Giá vào lệnh:** Ask cho Long và Bid cho Short, đúng thời điểm và quy ước fill của EA. Quy ước này
  phải được xác minh trong C1 (P3), không giả định.
- **Chi phí:** spread thực tế của bar/tick; commission và swap theo spec broker.
- **Hai barrier chạm trong cùng bar:** kế thừa quy ước hiện có `AMBIGUOUS_SAME_BAR`
  (`agent/phase3/outcomes/labels.py`). Nhãn bị loại khỏi phân loại, không gán thắng/thua.
- **Timeout:** không chạm barrier trong horizon thì nhãn phân loại là `0`; nhãn hồi quy dùng giá đóng
  cửa tại horizon.
- **Cuối dữ liệu chưa đủ horizon:** `INCOMPLETE`, loại khỏi train/test.
- **Thời điểm kết thúc nhãn** (`label_end_utc`): được lưu cho mọi nhãn để phục vụ purge (§5.3).

**Nhãn không phải mẫu.** Một opportunity có nhiều nhãn vẫn là **một** sự kiện. Mọi nhãn cùng event ở
cùng split và cùng block bootstrap. Báo cáo luôn ghi số event, không ghi số dòng nhãn.

### 5.3 C3 — Meta-labeling và walk-forward

**Câu hỏi:** với một tín hiệu engine RSI đã phát, (1) `take_probability`; (2) `expected_r` chỉ dùng để
xếp hạng và phân tích, **không** dùng để tăng risk.

**Model theo thứ tự độ phức tạp:** baseline hiện có (prior, regime prior, logistic, similarity); sau đó
gradient boosting nông có regularization mạnh. Chỉ chuyển lên model phức tạp hơn sau khi model đơn giản
hơn đã được đánh giá trên cùng split.

**Walk-forward với mốc thời gian chung cho mọi domain:**

```text
cửa sổ k:  mốc T_k chung cho mọi domain
  train   = mọi event của mọi domain có label_end_utc < T_k − embargo
  test    = mọi event của mọi domain có event_time trong [T_k, T_k + 1 tháng)
  dịch T_k thêm 1 tháng
```

- Purge theo **thời gian thực** từ event đến `label_end_utc`, không theo số bar cố định. `core_exit_r` có
  thể kéo dài quá 48 bar.
- Embargo tối thiểu bằng khoảng `label_end_utc − event_time` dài nhất trong cửa sổ train.
- **Feature point-in-time:** chỉ dùng thông tin đã có tại thời điểm quyết định. Nến H4/D1 chỉ dùng bar
  đã đóng. Swing chỉ dùng sau khi đã được xác nhận. Có unit test riêng cho từng loại feature.
- **Calibration và chọn ngưỡng/top-k** dùng một phần dữ liệu nội bộ tách riêng trong train (theo thời
  gian, phần cuối của train), không dùng test.
- **So sánh bắt buộc:** model chỉ train trên BTCUSD H1 so với model gộp nhiều domain, đánh giá trên
  BTCUSD H1. Kết quả tốt ở domain phụ không thay thế được bằng chứng trên domain mục tiêu.

**Đánh giá policy, không chỉ đánh giá điểm số.** Top-k có R trung bình cao hơn chưa đủ. Phải replay cả
chuỗi quyết định (qua C1, mức P3/P4) với cùng risk, giới hạn một position/group, sizing và chi phí, so với
V26 trên cùng dữ liệu. Model **không** được bỏ qua các chặn bắt buộc như `raw_lot_below_min_lot`, spread
hoặc margin.

**Tiêu chí kết luận:** khai báo trước theo §6.2.

| Trạng thái | Điều kiện |
|---|---|
| `EDGE` | Đạt mọi ngưỡng đã khai báo sau hiệu chỉnh, trên domain mục tiêu và ở cả Long lẫn Short |
| `NO_EDGE` | CI của chênh lệch so với baseline nằm trọn trong vùng tương đương đã khai báo trước |
| `INCONCLUSIVE` | Không thuộc hai trường hợp trên (ít dữ liệu, CI quá rộng) |

`NO_EDGE` và `INCONCLUSIVE` đều dừng việc nâng độ phức tạp model; báo cáo phải ghi đúng lý do.

### 5.4 C4 — Champion và challenger trên máy 1 (4D, chưa duyệt deploy)

- Collector chấm mỗi canonical opportunity bằng nhiều bundle đóng băng. Dự đoán bất biến sau khi commit.
- Trần kỹ thuật `N=5`; **ban đầu tối đa 2 challenger**.
- Challenger chỉ được thêm tại ranh giới kỳ. Mẫu đánh giá chỉ tính từ **sau** thời điểm đăng ký.
- Schema thêm `bundle_registry` và `predictions(bundle_id, canonical_opportunity_id, …)`, migration theo
  kiểu additive.

**Xét thăng hạng shadow:**

- `>=200` mẫu đã resolve kể từ khi đăng ký là **điều kiện tối thiểu để xét**, không phải bảo đảm đủ bằng
  chứng. Mốc 500 mẫu của Phase 5 **không** được thay bằng 200.
- Cùng nhãn mục tiêu, cùng tập opportunity sau đăng ký.
- Bootstrap **ghép cặp** theo khối thời gian.
- Lịch đánh giá cố định (ví dụ ngày 1 mỗi tháng). Không xem kết quả hằng ngày rồi chọn ngày đạt.
- Biên "không kém hơn" theo từng hướng được khai báo trước bằng số. Ví dụ: Brier của challenger không
  lớn hơn champion quá `+0.005` ở cả Long lẫn Short.
- Báo cáo độ phủ thời gian và mức bất định, không chỉ số dòng đã resolve.
- Thăng hạng chỉ đổi bundle **shadow**. Challenger cải thiện Brier vẫn phải chứng minh hiệu quả policy
  (§5.3) trước bất kỳ bước execution nào.

### 5.5 C5 — Vòng nghiên cứu do agent điều khiển

Chu trình: giả thuyết (ghi trước) → cấu hình (hash) → chạy C1/C2/C3 → ghi registry (kể cả thất bại)
→ đánh giá theo §6.2 → evidence pack → operator.

**Chỉ bật sau khi** C1 đạt parity trong phạm vi cần dùng, label manifest được duyệt và registry/holdout
đã được kiểm chứng tách quyền.

**Quyền của agent:**

- Được: đọc dataset (trừ holdout và outcome forward chưa đến lịch), chạy C1/C3, ghi registry, tạo
  preset/bundle **ứng viên** trên branch riêng, viết báo cáo.
- Không được: sửa `.mq5` hoặc preset đang forward, tạo authorization, thêm challenger, mở holdout, đọc
  outcome forward ngoài lịch, merge, bật bất kỳ thứ gì trên runtime.

**Bài học là kết quả gộp, không phải reflection theo từng mẫu.**

TradingAgents cho LLM viết 2–4 câu "bài học" sau **mỗi** quyết định dựa trên alpha 5 ngày của đúng quyết
định đó, rồi đưa các bài học gần nhất vào prompt. Cách này học từ nhiễu của từng mẫu và không có thống kê.
C5 không áp dụng cách đó:

- Đơn vị bài học là **một thí nghiệm** trong registry, kèm n (số event), CI, family và trạng thái hiệu
  chỉnh (§6.2). Không có bài học từ một lệnh hay một opportunity đơn lẻ.
- LLM được viết tóm tắt cho thí nghiệm, nhưng mọi khẳng định định lượng phải trích từ trường của registry.
  Văn bản không có số liệu đối chiếu được thì không được dùng làm căn cứ.
- Khi agent tìm bài học cho vòng mới, truy vấn registry theo family, giả thuyết hoặc domain, với
  `as_of` (§6.3), không chọn theo độ gần thời gian.
- Kết quả `NO_EDGE` và `INCONCLUSIVE` cũng là bài học và phải được trả về trong truy vấn, để agent không
  lặp lại giả thuyết đã thử.

**Nguồn gốc giả thuyết.** Mỗi giả thuyết ghi `hypothesis_origin`:
`HUMAN` (operator), `LLM_GENERATED`, hoặc `DATA_DERIVED` (sinh tự động từ thống kê trên dữ liệu không
thuộc holdout). Trường này quyết định holdout nào còn hợp lệ cho ứng viên (§6.1, §6.6).

---

## 6. Kiểm soát overfit

### 6.1 Holdout

- Holdout chỉ gồm dữ liệu `CLEAN` trong §2: lịch sử của ETHUSD, XAUUSD, EURUSD với **ngày bắt đầu và kết
  thúc cố định**, khóa trước lần train đầu tiên. Đề xuất: 12 tháng `2025-07-01` đến `2026-06-30` cho mỗi
  domain phụ.
- Dữ liệu và evaluator nằm ngoài quyền truy cập của agent. Khóa giải mã do operator giữ, tách khỏi
  nơi lưu dữ liệu.
- **Một ứng viên cuối đã đóng băng cho một đợt xác nhận.** Sau khi công bố kết quả, holdout được đánh
  dấu `CONSUMED` trong §2. Không mở lại cùng holdout cho ứng viên được chỉnh sau khi đã biết kết quả.
- Khi không còn lịch sử sạch, báo cáo phải ghi rõ: xác nhận độc lập chỉ còn dựa vào dữ liệu forward mới.
- Riêng BTCUSD H1 không có holdout lịch sử (§2) và chỉ xác nhận bằng forward.
- **Holdout lịch sử chỉ sạch với giả thuyết không do LLM tạo ra.** Với ứng viên có
  `hypothesis_origin=LLM_GENERATED`, mọi khoảng lịch sử trước mốc kiến thức của model sinh giả thuyết bị
  coi là đã nhiễm (§6.6). Ứng viên đó chỉ được xác nhận độc lập bằng dữ liệu **sau** mốc kiến thức, trên
  thực tế là dữ liệu forward.

### 6.2 Khai báo trước và hiệu chỉnh đa phép thử

Trước mỗi nhóm thí nghiệm, registry ghi:

- **Metric chính** (ví dụ: chênh lệch Brier so với unconditional prior trên BTCUSD H1) và metric phụ.
- **Nhóm phép so sánh** (family) mà kết quả thuộc về.
- **Phương pháp hiệu chỉnh** theo loại metric:
  - Metric xác suất (AUC, Brier, log-loss): CI block bootstrap kèm hiệu chỉnh Holm cho số phép so sánh
    trong family.
  - Metric lợi nhuận (Sharpe/PnL của policy): Deflated Sharpe Ratio với số phép thử cộng dồn.
  - Quá trình chọn phương án: Probability of Backtest Overfitting (CSCV) như một chẩn đoán, không phải
    ngưỡng duy nhất.
- **Ngưỡng quyết định** và vùng tương đương cho `NO_EDGE`.

Số phép thử phải tính mọi lựa chọn đã ảnh hưởng kết quả: label, feature set, top-k, siêu tham số, domain.

### 6.3 Registry và ngân sách

- Registry append-only, **hoạt động trước thí nghiệm model đầu tiên** (trước 4C), không chờ 4E.
- Mỗi bản ghi gồm: `experiment_id`, giả thuyết, family, metric chính, config hash, code SHA, dataset
  fingerprint, split và holdout version, dependency lock hash, kết quả, trạng thái
  (`REJECTED`/`CANDIDATE`/`PROMOTED`), lý do, `hypothesis_origin`, model và mốc kiến thức của LLM
  tham gia (nếu có).
- **Thời điểm biết được.** Mỗi kết quả ghi `known_at_utc`: thời điểm kết quả trở nên biết được đối với
  người hoặc agent (lúc thí nghiệm hoàn tất, hoặc lúc mở outcome forward theo lịch §6.4). Đây là tương
  đương của `resolution_date` trong TradingAgents.
- **Truy vấn `as_of`.** Khi một vòng nghiên cứu hoặc một mô phỏng quá trình nghiên cứu được thiết kế tại
  mốc T, agent chỉ đọc các kết quả có `known_at_utc <= T`. Bản ghi thiếu `known_at_utc` bị loại khỏi
  truy vấn `as_of` (di chuyển dữ liệu theo hướng bảo thủ).
- **Kỹ thuật lưu trữ:** append-only, ghi atomic (file tạm rồi `replace`), khóa một tiến trình ghi tại một
  thời điểm, idempotent theo `experiment_id`. Bản ghi đã có kết quả không bị sửa; đính chính là một bản
  ghi mới tham chiếu bản cũ.
- Ngân sách: trần `K=50` mỗi vòng; **vòng đầu tối đa 20**. Tổng số phép thử trên cùng dữ liệu được
  **cộng dồn qua các vòng**, không đặt lại về 0.

### 6.4 Bảo vệ dữ liệu forward

Dữ liệu forward trên máy 1 là holdout thật duy nhất của BTCUSD H1.

- Máy 2 và agent chỉ nhận **health/coverage** (heartbeat, số event, độ trễ, lỗi). Không nhận outcome
  hay chất lượng dự đoán ngoài lịch.
- Outcome và metric dự đoán chỉ được mở theo **lịch đánh giá cố định**, ghi trước vào registry.
- Mỗi lần mở được ghi lại. Mọi thí nghiệm thiết kế sau lần mở đó được coi là đã "thấy" khoảng forward
  tương ứng.

### 6.5 Môi trường tái lập

- Máy 2 dùng môi trường Python riêng, khóa phiên bản (lock file có hash).
- Dependency ban đầu: NumPy, pandas, SciPy, scikit-learn. LightGBM chỉ thêm khi có nhu cầu đã khai báo
  trong registry.
- Runtime máy 1 giữ tối thiểu, không thêm dependency research.
- Evidence pack ghi lock hash của môi trường.

### 6.6 Rò rỉ qua kiến thức sẵn có của LLM

Bộ lọc thời gian chỉ chặn được rò rỉ từ **dữ liệu đưa vào**. Nó không chặn được những gì LLM đã học từ
dữ liệu huấn luyện. Một LLM có mốc kiến thức tháng 06/2026 có thể đã "biết" diễn biến BTC, ETH, vàng và
EURUSD trong 2025–2026, kể cả khi agent chỉ được cấp dữ liệu đến 2024. TradingAgents gặp đúng giới hạn
này: bộ lọc `as_of` của họ chặn bài học có kết quả sau ngày run, nhưng agent và reflector vẫn là LLM viết
ở hiện tại về quá khứ.

Áp dụng cho Phase 4:

| Quy định | Nội dung |
|---|---|
| Ghi mốc kiến thức | Mọi bước có LLM tham gia (sinh giả thuyết, chọn feature, viết tóm tắt dùng làm căn cứ) ghi model id và mốc kiến thức đã công bố vào registry |
| Holdout theo nguồn gốc | `LLM_GENERATED`: chỉ dữ liệu sau mốc kiến thức là sạch. `HUMAN` và `DATA_DERIVED`: dùng holdout §6.1 như bình thường. Operator chịu trách nhiệm xác nhận một giả thuyết thật sự là `HUMAN` |
| Không dùng LLM ở vòng chấm điểm | Evaluator, nhãn, metric và quyết định PASS/FAIL là code tất định, không gọi LLM |
| LLM không chấm runtime | Collector và bundle trên máy 1 không gọi LLM. Dự đoán phải tái lập được từ bundle đã đóng băng |
| Đổi model | Khi đổi sang model có mốc kiến thức mới hơn, mọi khoảng lịch sử trước mốc mới bị coi là đã nhiễm đối với giả thuyết do model đó sinh ra |
| Báo cáo | Evidence pack của ứng viên `LLM_GENERATED` ghi rõ: kết quả trên lịch sử trước mốc kiến thức chỉ có giá trị sàng lọc, không phải xác nhận độc lập |

Hệ quả: dữ liệu forward do máy 1 thu từ 2026-10 là nguồn xác nhận sạch duy nhất cho mọi ứng viên do agent
đề xuất. Điều này củng cố quyết định bảo vệ outcome forward ở §6.4.

---

## 7. Cổng

```text
G0  Parity C1 PASS trong phạm vi cần dùng (P1/P2 cho tín hiệu; P3/P4 cho policy/PnL)
G1  Walk-forward OOS đạt tiêu chí đã khai báo (§5.3, §6.2)
G1b Kiểm tra tích hợp ứng viên bằng MT5 trên dữ liệu development (trước khi dùng holdout)
G2  Holdout domain sạch (§6.1): một đợt cho một ứng viên đóng băng
G3  MT5 Tester real ticks xác nhận (report gate README §5, audit ON/OFF khớp)
G4  [nếu là bundle shadow] Challenger trên máy 1 theo §5.4
──────────────── kết thúc phạm vi Phase 4 ────────────────
G5  QUYẾT ĐỊNH OPERATOR RIÊNG: đưa preset/version mới vào forward demo
```

**G5 không thuộc Phase 4.** Phase 4 chỉ chuẩn bị evidence và đề xuất. Quyết định G5 phải ghi rõ: tài khoản
demo, preset/bundle SHA, giới hạn risk, thời hạn mẫu, điều kiện dừng và rollback. Thăng hạng bundle
shadow (G4) **không** cấp quyền đưa preset execution vào demo.

---

## 8. Kế hoạch

| Phase | Nội dung | Máy | Cổng thoát | Trạng thái duyệt |
|---|---|---|---|---|
| 4.0 | Collector Phase 3.1 thu dữ liệu forward thật | 1 | `FORWARD_COLLECTION_STATUS=ACTIVE`, heartbeat ổn định | Chỉ thị operator 2026-10-01 |
| 4R | Registry, preregistration, khóa split/holdout | 2 | Holdout tách quyền đã được kiểm chứng; §2 được ký | Được duyệt |
| 4A | C1 engine và parity harness | 2 | P1/P2 PASS; sau đó P3/P4 với tick export | Được duyệt (offline) |
| 4B | Kiểm kê dữ liệu 4 domain | 1 export → 2 | Báo cáo kiểm kê §5.2 | Được duyệt (kiểm kê) |
| 4B+ | Label manifest và dựng nhãn | 2 | Leakage gate PASS; `core_exit_r` chỉ sau P3/P4 | Sau 4A |
| 4C | Meta-labeling walk-forward | 2 | `EDGE` / `NO_EDGE` / `INCONCLUSIVE` | Chưa duyệt; cần 4R |
| 4D | Multi-bundle collector | 2 → 1 | Replay/idempotency/immutability PASS | Chưa duyệt |
| 4E | Agent research loop | 2 | Mục §5.5 | Chưa duyệt |

Thứ tự bắt buộc: 4R trước 4C; P3/P4 trước nhãn `core_exit_r`; 4E sau cùng.

**Điểm quyết định:** 4C ra `NO_EDGE` hoặc `INCONCLUSIVE` thì dừng hướng meta-labeling với feature hiện tại.
Ưu tiên chuyển sang chất lượng tín hiệu gốc và feature mới.

---

## 9. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Engine Python lệch MT5 | Parity theo phạm vi §5.1; chạy lại khi `.mq5` đổi; G3 luôn xác nhận bằng MT5 |
| Overfit do nhiều thí nghiệm | §6: holdout một lần, khai báo trước, hiệu chỉnh theo loại metric, ngân sách cộng dồn |
| Rò rỉ giữa domain trong model gộp | Mốc thời gian chung, purge theo `label_end_utc` (§5.3) |
| Nhãn đếm trùng mẫu | Một event một nhóm split/bootstrap (§5.2) |
| EA không chuyển giao sang mã khác | Kiểm kê domain trước khi gộp; so sánh model chỉ BTC với model gộp |
| Dữ liệu forward bị nhiễm | §6.4: chỉ health/coverage; outcome theo lịch |
| LLM đã biết giai đoạn holdout từ dữ liệu huấn luyện | §6.6: ghi nguồn gốc giả thuyết và mốc kiến thức; ứng viên `LLM_GENERATED` chỉ xác nhận bằng dữ liệu sau mốc |
| Học từ nhiễu của từng mẫu | §5.5: bài học là thí nghiệm có n và CI; không dùng reflection theo từng mẫu |
| Agent dùng kết quả chưa biết tại thời điểm thiết kế | §6.3: `known_at_utc` và truy vấn `as_of` |
| Agent vượt quyền | §5.5; runtime chỉ nhận config có hash và operator duyệt |
| Kỳ vọng sai | Mọi báo cáo ghi: kết quả backtest và shadow không phải lợi nhuận thực thi |

---

## 10. Quyết định operator đã ghi nhận (2026-10-01)

| # | Quyết định |
|---|---|
| 1 | Universe đợt 1: BTCUSD, ETHUSD, XAUUSD, EURUSD với `EntryTF=H1`. Ưu tiên broker/server đang dùng cho demo baseline nếu lịch sử đủ tốt |
| 2 | Holdout: 12 tháng cố định, chỉ với domain `CLEAN`; một ứng viên một đợt; BTCUSD H1 xác nhận bằng forward |
| 3 | Ngân sách: trần K=50, vòng đầu 20, cộng dồn. Challenger: trần N=5, ban đầu ≤2 |
| 4 | Dependency: cho phép trên máy 2, môi trường riêng có lock; NumPy, pandas, SciPy, scikit-learn; LightGBM khi cần |
| 5 | Bắt đầu 4A song song với 4.0. Kiểm kê 4B song song. `core_exit_r` chờ P3/P4 |

Không có phần nào trong tài liệu này được coi là bằng chứng edge, giấy phép forward mới cho preset
execution hay chấp thuận giao dịch.
