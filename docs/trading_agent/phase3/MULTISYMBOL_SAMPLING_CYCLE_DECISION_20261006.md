# Chu kỳ lấy mẫu và lịch xem kết quả — ETHUSD, XAUUSD, EURUSD H1 (MT5-DATA)

Trạng thái: `PROPOSED / CHỜ OPERATOR DUYỆT` (2026-10-06)
Liên quan: `MACHINE1_MULTISYMBOL_COLLECTION_20261006.md`, Phase 4 design §5.2, §6.3, §6.4, §6.6.

Tài liệu này trả lời câu hỏi của máy 1: các mã trên MT5-DATA được lấy mẫu theo chu kỳ nào, và khi nào được
xem kết quả. Phần **thu dữ liệu không phụ thuộc quyết định này**: máy 1 cứ để EA và task snapshot chạy.
Quyết định chỉ chi phối *khi nào được nhìn* vào dữ liệu.

## 1. Những gì không thuộc chu kỳ này

- Gate 500 mẫu của Phase 3 chỉ áp cho bundle BTCUSD (V26/V63). Bundle đó không được huấn luyện trên ETH,
  XAU, EUR nên **không chạy collector Phase 3 và không có dự đoán** cho ba mã này.
- Không có "chu kỳ mẫu" kiểu campaign. Không có `campaign_id`, `prepare-forward` hay authorization cho MT5-DATA.
- PnL của tài khoản demo thứ ba không phải bằng chứng và không được báo cáo.

## 2. Đơn vị mẫu và mốc bắt đầu

| Mục | Quy định |
|---|---|
| Mẫu | Một `canonical_opportunity_id` trong luồng `phase3-opportunity-observation/1`; không đếm số dòng nhãn hay số lệnh |
| Domain | `(symbol, EntryTF=H1)`: ETHUSD, XAUUSD, EURUSD |
| `forward_start_utc` | `2026-10-05T18:02:42Z` (Algo Trading được bật). Bản ghi có thời điểm sự kiện trước mốc này bị loại. Máy 1 đã báo các file lúc đó đều 0 byte nên không có bản ghi nào bị loại |
| Nguồn sự thật | Snapshot hằng ngày (`phase4-data\snapshots`, `manifest.csv` có SHA-256), không phải file đang được EA ghi |
| Khoảng trống | Nếu EA/terminal ngừng, ghi lại khoảng trống từ log và manifest. Không backfill, không suy diễn |

## 3. Chu kỳ

| Việc | Chu kỳ | Nội dung được phép | Người làm |
|---|---|---|---|
| Snapshot dữ liệu | Hằng ngày 00:30 giờ máy (task đã cài) | Copy file, SHA-256, số dòng | Task trên máy 1 |
| Báo cáo **sức khỏe** | Hằng tuần (thứ Hai) và khi có sự cố | Số dòng mỗi domain, EA còn chạy, khoảng trống, lỗi Journal | Máy 1, viết vào branch `ops/...` |
| **Kiểm kê C2** (không dùng outcome) | Lần đầu sau 30 ngày (**2026-11-05**), sau đó mỗi tháng | Số tín hiệu theo tuần; tỷ lệ `raw_lot_below_min_lot`; phân phối SL/ATR và spread/R; tỷ lệ Long/Short; spec hợp đồng | Máy 2 |
| **Outcome và metric dự đoán** | **Chỉ khi đủ cả hai điều kiện** bên dưới | Nhãn, hit rate, metric | Máy 2, ghi trước vào registry |

Điều kiện mở outcome cho một domain:

1. Đã qua **2027-01-05** (tối thiểu 3 tháng), và
2. Domain có ít nhất **200 `canonical_opportunity_id` đã đủ thời gian resolve** (48 nến H1 sau sự kiện).

Hai điều kiện áp dụng riêng từng domain. Sau lần mở đầu, lặp lại mỗi quý, mỗi lần được ghi vào registry
(§6.3 thiết kế) cùng `known_at_utc`. Không xem kết quả ngoài các mốc này, và không đổi mốc sau khi đã thấy
bất kỳ outcome nào.

## 4. Lý do chọn các mốc

- **30 ngày cho kiểm kê:** ETH và XAU phát tín hiệu ít, nên một tuần là quá ít để phân phối có ý nghĩa; kiểm kê
  không dùng outcome nên không làm hỏng độ sạch của forward.
- **200 mẫu và 3 tháng cho outcome:** đây là điều kiện *tối thiểu để xét* (cùng tinh thần mốc 200 của
  §5.4 thiết kế), không phải bảo đảm đủ bằng chứng. Số mẫu thực tế mỗi ngày chưa được đo; nếu sau 30 ngày
  một domain có tốc độ quá thấp để đạt 200 mẫu trong một năm, ghi vào kiểm kê và để operator quyết định
  (kéo dài, bỏ domain hoặc đổi chiến lược thu), không hạ ngưỡng.
- **Xác nhận độc lập:** dữ liệu này phát sinh sau mốc kiến thức của LLM tham gia thiết kế (§6.6), nên là
  nguồn xác nhận sạch cho các giả thuyết do LLM sinh ra.

## 5. Việc máy 1 cần làm

Không có việc mới ngoài những gì đã làm. Giữ EA và task snapshot chạy; báo cáo sức khỏe hằng tuần theo §3;
ghi sự cố (EA dừng, terminal khởi động lại, mất kết nối) kèm giờ UTC. Không đưa outcome, PnL hay nội dung
JSONL vào báo cáo.

## 6. Cần operator xác nhận

Các mốc trong §3 và §4 là **đề xuất**. Sau khi operator duyệt, ghi vào registry (khi có) trước lần xem đầu tiên.
Mốc nào operator muốn đổi thì đổi *trước* 2026-11-05.
