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

## Cập nhật 2026-10-06: contract spec v2 (tick value và giờ giao dịch)

Đọc bằng script trong terminal MT5-DATA lúc 2026-10-05T18:13:45Z, lưu ở `D:\Trading\build-bot-runtime\phase4-data\contract_specs_20261006_v2.json` (schema `machine1-contract-specs/2`). Không có tài khoản hay server.

| Mã | contract size | digits | point | tick size | tick value | min lot | step | spread hiện tại (points) |
|---|---|---|---|---|---|---|---|---|
| ETHUSD | 1 | 2 | 0.01 | 0.01 | 0.01 | 0.1 | 0.01 | 70 |
| XAUUSD | 100 | 3 | 0.001 | 0.001 | 0.1 | 0.01 | 0.01 | 168 |
| EURUSD | 100000 | 5 | 0.00001 | 0.00001 | 1.0 | 0.01 | 0.01 | 6 |

Giờ giao dịch theo giờ server của broker (server trừ UTC = 0 giây tại thời điểm đo):

- **ETHUSD:** 24/7 (00:00-00:00 mọi ngày).
- **XAUUSD:** CN 22:01-24:00; T2–T5 00:00-20:58 và 22:00-24:00; T6 00:00-20:58; T7 nghỉ.
- **EURUSD:** CN 21:05-24:00; T2–T5 24h; T6 00:00-20:59; T7 nghỉ.

Lưu ý: spread XAUUSD lúc đo (168 points) cao vì ngoài giờ thanh khoản; không dùng làm đại diện. Sau khi đọc spec, MT5-DATA được khởi động lại một lần (bình thường).

## Task đã cài (operator đồng ý 2026-10-05)

- `BuildBot-Phase4-DataSnapshot`: hằng ngày 00:30 giờ máy, chạy thử thành công; snapshot đầu có 3 file 0 dòng.
- `BuildBot-MT5-DATA-Autostart`, `BuildBot-MT5-V26-Autostart`, `BuildBot-MT5-V63-Autostart`: mở terminal khi đăng nhập Windows (chờ 30s/30s/45s). Chưa thử; lần khởi động lại máy đầu tiên là lần thử thật.

## Cập nhật 2026-10-08: sau 24 giờ chạy liên tục của MT5-DATA

Số liệu lúc 2026-10-08T16:17Z. MT5-DATA chạy liên tục từ 2026-10-07T15:15Z (mở bằng scheduled task); Algo Trading do operator bật 15:20Z. Không đưa vào báo cáo nội dung JSONL, outcome hay PnL.

| File (magic) | Số dòng opportunity | Ghi chú |
|---|---|---|
| `...26072701_ETHUSD_H1.jsonl` | 1 | bản ghi duy nhất xuất hiện 2026-10-07 07:00Z, trước lần mở lại |
| `...26072702_XAUUSD_H1.jsonl` | 0 | |
| `...26072703_EURUSD_H1.jsonl` | 0 | |

- Trong 25 giờ chạy liên tục không có dòng nào mới ở ba file. Điều kiện dừng "0 dòng sau 72 giờ khi thị trường mở" **chưa đủ** vì MT5-DATA bị tắt từ 2026-10-05T21:43Z đến 2026-10-07T15:15Z; thời gian EA thực sự chạy cho XAUUSD/EURUSD tới nay khoảng 1,5 ngày. Đây vẫn chưa là kết luận về tần suất tín hiệu của chiến lược trên các mã này.
- Snapshot hằng ngày: đã chạy các ngày 2026-10-06 (17:30Z) và 2026-10-07 (17:30Z); manifest ghi đủ ba file mỗi lần (ETH 1 dòng, XAU/EUR 0 dòng).
- MT5-DATA từng tắt hai lần (21:43Z ngày 05/10; 07:00Z ngày 07/10). Lần thứ hai có lệnh demo ETHUSD mở lúc 07:00Z (bán 0.3, rủi ro 0,5%) trước khi terminal tắt, nằm không có EA quản lý khoảng 8 giờ đến lúc mở lại. Nghi terminal bị tắt theo phiên làm việc của agent vì được mở từ phiên đó; từ 2026-10-07T15:15Z được mở bằng task nên chạy độc lập, chạy liên tục sau đó.
