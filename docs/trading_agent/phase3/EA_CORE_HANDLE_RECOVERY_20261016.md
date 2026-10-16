# EA — Tự phục hồi handle chỉ báo lõi (sửa lỗi MISSING_STATE)

Trạng thái: `CODE_READY / CHỜ PARITY / CHƯA TRIỂN KHAI` (2026-10-16)
Branch: `fix/ea-core-handle-recovery`

## 1. Sự cố

Trên MT5-DATA, XAUUSD và EURUSD không ghi được bản ghi opportunity nào từ 2026-10-07T15:20Z đến
2026-10-14T11:00Z. `DIAG_SUMMARY` cho thấy `missingStateBars` 111 và 116: mọi nến H1 đều thất bại ở
`BuildState`. Lịch sử đủ 260 nến ở cả 4 khung, và handle RSI/ATR mới tạo bằng script vẫn trả đủ dữ liệu.
Khởi tạo lại EA thì hết lỗi (báo cáo máy 1, cập nhật 2026-10-14).

## 2. Nguyên nhân

EA tạo `rsiHandles[]`/`atrHandles[]` cho D1/H4/H1/M15 **một lần** trong `OnInit` và không bao giờ tạo
lại. Khi terminal vừa khởi động và lịch sử chưa đồng bộ, handle có thể kẹt: `CopyBuffer` trả ít hơn 260
giá trị mãi mãi. `BuildState` trả `false`, `OnTick` chỉ tăng `diagForwardMissingStateBars` và thoát,
không có cảnh báo. Lỗi này áp dụng cho mọi terminal, kể cả V26/V63 sau mỗi lần khởi động lại.

## 3. Bản sửa

| Thành phần | Nội dung |
|---|---|
| Input mới | `CoreHandleRecoveryBars = 3` (0 = tắt). Preset cũ không có dòng này nên dùng mặc định 3; hash preset không đổi |
| `CheckCoreIndicatorHandles()` | Gọi mỗi nến `EntryTF` mới, trước các audit. Với từng khung: nếu `Bars >= 260` mà `CopyBuffer` RSI hoặc ATR vẫn thiếu, tăng bộ đếm và in `CORE_HANDLE_STALE` (kèm `BarsCalculated`). Đủ `CoreHandleRecoveryBars` lần liên tiếp thì tạo lại handle |
| `RecreateCoreHandles()` | `IndicatorRelease` handle cũ **trước**, rồi mới `iRSI`/`iATR` (MT5 dùng chung instance cho chỉ báo cùng tham số; tạo trước khi giải phóng có thể nhận lại đúng instance đang kẹt). In `CORE_HANDLE_RECREATED` hoặc `CORE_HANDLE_RECREATE_FAILED` |
| Thiếu lịch sử thật | Nếu `Bars < 260`, không tạo lại handle (không giúp được) và không đếm |
| `DIAG_SUMMARY forward` | Thêm `coreHandleStaleChecks`, `coreHandleRecreated`, `coreHandleRecreateFailed` |

**Vì sao không đổi hành vi giao dịch khi handle khỏe:** hàm chỉ đọc (`Bars`, `CopyBuffer` vào mảng tạm)
cho tới khi handle đã hỏng đủ 3 nến. Lúc đó EA vốn đang bỏ mọi nến (`MISSING_STATE`), nên bản gốc không
giao dịch. Bản sửa chỉ khác bản gốc ở trường hợp này: nó tự phục hồi thay vì kẹt mãi.

Không đổi: logic tín hiệu, sizing, SL/TP, exit, pyramiding, schema telemetry, chuỗi phiên bản chiến lược
(nên `canonical_opportunity_id` không đổi).

## 4. Đã kiểm chứng (máy 2)

```text
MetaEditor (outputs/build/mt5-latest), include mt5-v82-runtime
  baseline (main)   0 errors, 0 warnings   ex5 BE7979BDD6F5473D6FA33BD8600E9C811D132C61FDFD98F8B53BF414B92C3AC0
  candidate         0 errors, 0 warnings   ex5 E9568DAECBF5AB8FCC054FA7E61A91F173802F7F8FE5DDFD3DA5C32EC8D5DF5D
```

**Chưa chạy Strategy Tester trên máy 2:** cấu hình tester ở đây đăng nhập server tài khoản thật; agent
không khởi động terminal với tài khoản thật.

## 5. Cần làm trước khi merge: parity (máy 1, terminal demo)

Chạy trên terminal demo V26 (`D:\Trading\MT5-V26`), không dùng terminal của tài khoản thật.

1. Checkout branch `fix/ea-core-handle-recovery` vào **clone báo cáo** (`D:\Trading\build-bot-reports`),
   không đụng checkout runtime.
2. Compile baseline (`main`) và candidate bằng MetaEditor của terminal đó, đặt tên khác nhau trong
   `MQL5\Experts\` (ví dụ `ParityBaseline.ex5`, `ParityCandidate.ex5`). Cả hai phải `0 errors, 0 warnings`.
3. Strategy Tester, cùng cấu hình cho cả hai: BTCUSD H1, `Model=4` (real ticks), deposit 5,000 USD,
   leverage 1:10, preset `83_v26_forward_demo_p3obs.set` rồi `84_v63_forward_demo_p3obs.set`.
   Khoảng ngày: tối thiểu `2023.04.01–2023.12.31` (cùng cửa sổ parity Phase 3.1); nếu thời gian cho phép
   thêm `2025.01.01–2026.07.01`.
4. So sánh bằng `tools/mt5/compare_execution_regression.py` và journal: số lệnh, deal, signal, Net, PF, DD
   phải **giống hệt**. Journal candidate được phép có thêm dòng `CORE_HANDLE_*`; mọi khác biệt khác là FAIL.
5. Ghi kết quả vào báo cáo ops: hash `.ex5` hai bản, report path, bảng so sánh, số dòng `CORE_HANDLE_*`.

## 6. Triển khai (sau khi parity PASS và operator duyệt)

1. **MT5-DATA trước** (nơi xảy ra lỗi, không phải mẫu đối chứng): compile, gắn lại EA trên 3 chart.
2. Kiểm chứng thực tế: lần khởi động lại terminal kế tiếp, journal không còn chuỗi `MISSING_STATE` kéo dài;
   nếu có `CORE_HANDLE_RECREATED` thì bản sửa đã phát huy tác dụng.
3. **V26/V63:** đây là build mới trên terminal đang chạy mẫu forward. Theo README §8, ghi ngày đổi build,
   SHA source và hash `.ex5` vào nhật ký forward. Do bản sửa không đổi hành vi khi handle khỏe (đã chứng
   minh bằng parity), mẫu forward hiện tại được giữ nguyên; operator quyết định thời điểm triển khai.
4. Collector Phase 3 không cần đổi (schema và canonicalizer không đổi), không cần `prepare-forward` lại
   vì chỉ `.ex5` trên terminal thay đổi. Checkout runtime chỉ cần cập nhật ở lần bảo trì kế tiếp.
