# Machine 1 — Thu dữ liệu forward ETHUSD, XAUUSD, EURUSD H1 (báo cáo ban đầu, 2026-10-06)

Theo `docs/trading_agent/phase3/MACHINE1_MULTISYMBOL_COLLECTION_20261006.md`. Báo cáo không có nội dung JSONL, outcome, PnL, số tài khoản hay server.

## Môi trường

- Terminal thứ ba: `D:\Trading\MT5-DATA`, chạy chế độ portable, data folder riêng trong thư mục đó. Tạo bằng cách copy chương trình (`terminal64.exe`, `MetaEditor64.exe`, `metatester64.exe`, `Sounds`) từ bản V26, SHA-256 `terminal64.exe` và `MetaEditor64.exe` khớp V26. Không copy cấu hình, dữ liệu hay tài khoản; chỉ chép `servers.dat` (danh sách server broker) từ V26 để đăng nhập được broker.
- Tài khoản demo thứ ba, kiểu **Hedge**, do operator đăng nhập (agent không nhập mật khẩu). Xác nhận demo bằng tiêu đề cửa sổ và Journal (`demo account - hedging mode`); số tài khoản khác V26 và V63.
- Repo: `D:\Trading\buildbot` ở `258b550384ebed08c6e0516b951a55d38d6a906f`.

## Symbol thật của broker

| Mã | Symbol broker | Ghi chú |
|---|---|---|
| ETH | `ETHUSD` | không hậu tố |
| XAU | `XAUUSD` | broker còn có `XAUUSD247`, **không dùng** |
| EUR | `EURUSD` | không hậu tố |

Không có mã nào bị bỏ.

## Hash

| Mục | SHA-256 |
|---|---|
| Blob source EA | `49f924e3927d8cb3ee1ee4b7369fd8294b030c9f` (khớp) |
| Preset 85 (ETHUSD, magic 26072701) | `21ae002537bf61b76bfc81f336d8ae1c07527827f796b1445ebd57bbf837d120` (khớp) |
| Preset 86 (XAUUSD, magic 26072702) | `31ecff1b79ad05b3da9ac53840b71701ec34679e9d8f525197b9293b51d363aa` (khớp) |
| Preset 87 (EURUSD, magic 26072703) | `34acce60621a2bc7cf72c11fca8c1bb40a7a4db882013fa268c88439a4d8a229` (khớp) |
| `.ex5` (compile bằng MetaEditor của MT5-DATA, 0 errors, 0 warnings) | `8bc81e8b8a761e3cf0043d2703e47292ed7cea83ebd0fb576f6ec6f182e879b6` |

## Gắn EA

- EA được gắn lên ba chart H1 lúc **2026-10-05T17:59:29Z**. Journal xác nhận từng EA khởi tạo, và mỗi cái mở đúng `Mentor_RSI_MTF_<magic>_<symbol>_H1.jsonl` (telemetry và opportunity) theo bảng trên. Đối chiếu Inputs: preset nạp 93 input, `MagicNumber` đúng, `ExportPhase3OpportunityJsonl=true`.
- Algo Trading được operator bật lúc **2026-10-05T18:02:42Z**. Operator bật/tắt lại lúc 18:04. Chưa có lệnh hay lỗi risk nào trong Journal tại thời điểm báo cáo.
- Contract spec (không có tài khoản/server): `D:\Trading\build-bot-runtime\phase4-data\contract_specs_20261006.json`. `tick_value` đo lúc chưa có tick nên bằng 0, và **thiếu giờ giao dịch**; cần bổ sung.

## Sai lệch so với tài liệu

1. **Cách gắn EA:** không có công cụ điều khiển giao diện MT5, nên chart và EA được gắn bằng hai script do agent viết đặt trong `MT5-DATA\MQL5\Scripts` (`ExportContractSpecs`, `ApplyDataCharts`) và ba template `mentor_{eth,xau,eur}.tpl` dựng từ nội dung preset 85/86/87 (không sửa preset). Terminal phải khởi động bằng `terminal64.exe /portable /config:start_apply.ini` để dựng lại đúng ba chart (script đóng các chart khác trước để không có EA trùng magic).
2. **Sự cố thử nghiệm:** khoảng 00:56–00:59 giờ máy ngày 06/10 (17:56–17:59Z), ETH và XAU có lúc chạy hai bản EA trùng magic do chart thừa trong profile. Các file opportunity đều 0 byte nên không có bản ghi trùng.
3. **`MT5-DATA` chưa tự khởi động và task snapshot chưa cài:** chờ operator đồng ý (bước 12–13 của tài liệu).
4. **Min lot ETHUSD là 0.1**, cao hơn EA dùng cho BTCUSD, nên lệnh ETH sẽ bị làm tròn lên mức tối thiểu.

## Còn thiếu (cập nhật sau)

- Trạng thái task snapshot hằng ngày và số dòng mỗi file sau 24 giờ.
- Giờ giao dịch từng mã và `tick_value`.
