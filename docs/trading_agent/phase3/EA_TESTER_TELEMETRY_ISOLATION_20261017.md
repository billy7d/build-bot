# EA — Tách file opportunity khi chạy Strategy Tester

Trạng thái: `CODE_READY / CHỜ KIỂM CHỨNG TRÊN MÁY 1` (2026-10-17)
Branch: `fix/ea-tester-telemetry-isolation` (dựa trên `main` `5ec8c85`, đã có bản sửa core-handle)

## 1. Sự cố

Ngày 2026-10-16, khi chạy parity cho bản sửa core-handle, một lần chạy tester với preset 83
(`ExportPhase3OpportunityInTester=true`) đã ghi **26 dòng backtest năm 2023 vào file JSONL live của V26**
(`Mentor_RSI_MTF_26072626_BTCUSD_H1.jsonl`, dòng 38–63). Lý do: exporter ghi vào `FILE_COMMON`, thư mục
dùng chung cho mọi terminal kể cả bản sao portable chạy tester, và tên file chỉ dựa vào magic, symbol,
timeframe. Collector đã loại các dòng này (`REJECTED_STALE`); operator quyết định để nguyên file.

## 2. Bản sửa

| | Live (không đổi) | Strategy Tester (mới) |
|---|---|---|
| Thư mục | `phase3/opportunities/` | `phase3/tester/opportunities/` |
| Cờ mở file | `FILE_READ \| FILE_WRITE \| ... \| FILE_SHARE_READ \| FILE_SHARE_WRITE`, append | `FILE_WRITE \| ...`, ghi mới mỗi lần chạy |

- Live: đường dẫn và cờ mở file giống hệt trước, nên collector và task snapshot không phải đổi cấu hình.
- Tester: không thể chạm vào file live; mỗi lần chạy có file sạch, không trộn kết quả run trước.
- Telemetry cũ `phase3-live-telemetry/1` vốn đã tắt trong tester nên không cần sửa.
- Không đổi logic tín hiệu, sizing, exit hay schema bản ghi.

Compile trên máy 2 (MetaEditor `outputs/build/mt5-latest`): `0 errors, 0 warnings`.

## 3. Kiểm chứng (máy 1, bản sao tester cô lập, tài khoản demo)

Dùng lại bản sao `D:\Trading\parity-v26-coreh-20261016` (hoặc một bản sao mới), không chạy trong terminal
V26/V63/MT5-DATA đang live. Làm việc trong clone báo cáo.

1. Ghi lại kích thước và SHA-256 của các file live trong
   `%APPDATA%\MetaQuotes\Terminal\Common\Files\phase3\opportunities\` (V26, V63, ETH, XAU, EUR).
2. Compile baseline (`main`) và candidate (branch này), `0 errors, 0 warnings`.
3. Chạy V26, BTCUSD H1, `Model=4`, cửa sổ `2023.04.01–2023.12.31`, preset 83 **giữ nguyên**
   `ExportPhase3OpportunityInTester=true` cho candidate.
   - Với baseline, **không** chạy với cờ này bật (đó chính là lỗi). Baseline dùng bản sao preset đã đổi cờ
     thành `false`, như lần parity trước.
4. So sánh baseline và candidate bằng `tools/mt5/compare_execution_regression.py --require-diagnostics`
   và diff journal: lệnh, deal, cycle, Net/PF/DD, diagnostics phải giống hệt. Bỏ qua các dòng log khác
   nhau do đường dẫn exporter.
5. Kiểm tra:
   - mọi file live ở bước 1 có kích thước và SHA-256 **không đổi**;
   - candidate tạo `phase3/tester/opportunities/Mentor_RSI_MTF_26072626_BTCUSD_H1.jsonl`, có bản ghi
     `phase3-opportunity-observation/1`;
   - chạy candidate lần hai: file tester bị ghi đè (số dòng như lần một, không gấp đôi).
6. Ghi kết quả vào báo cáo ops (không ghi giá trị Net/PF/DD, không ghi nội dung JSONL).

## 4. Triển khai

Bản sửa chỉ đổi hành vi khi chạy tester. Các terminal live **không cần** cập nhật `.ex5` vì bản sửa này;
chúng sẽ nhận nó cùng lần cập nhật EA kế tiếp. Sau khi merge, mọi lần chạy tester trên máy 1 không còn
cần đổi `ExportPhase3OpportunityInTester=false` để bảo vệ file live.
