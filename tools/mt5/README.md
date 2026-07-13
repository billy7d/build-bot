# Môi trường compile và backtest MQL5 tự động

Bộ công cụ này dùng trực tiếp bản MetaTrader 5 và Wine prefix đang có trên máy. Không cài thêm một terminal riêng, nhờ vậy vẫn dùng đúng dữ liệu BTCUSD, cấu hình broker và các local agent hiện tại.

## Compile EA

```bash
./tools/mt5/compile.sh
```

Script compile `outputs/Mentor_RSI_MTF_v1.mq5`, kiểm tra bắt buộc `0 errors, 0 warnings`, rồi đồng bộ `.mq5` và `.ex5` vào `MQL5/Experts/Advisors` của MT5. Log được lưu tại `outputs/build/compile.log`.

## Chạy một preset

```bash
./tools/mt5/backtest.sh outputs/presets/22_v11_pyramid_control_off.set \
  --from 2019.01.01 \
  --to 2022.12.31 \
  --deposit 1000 \
  --leverage 1:10 \
  --symbol BTCUSD \
  --period H1 \
  --model 4
```

`--model 4` là chế độ Every tick based on real ticks. Kết quả mỗi lần chạy nằm trong `backtests/<tên-run>/`, gồm:

- `report.html`: báo cáo Strategy Tester đầy đủ.
- `summary.txt` và `summary.json`: các chỉ số chính, Long/Short PF và tỷ trọng lệnh thắng lớn nhất.
- `journal-summary.txt`: các dòng kết thúc test và toàn bộ `DIAG_SUMMARY source=OnTester`.
- `tester-config.ini`: điều kiện test đã dùng.
- Bản sao preset để truy vết chính xác cấu hình.

MT5 terminal phải được đóng trước khi chạy. Script chủ động dừng nếu phát hiện `terminal64.exe` đang mở để tránh can thiệp vào phiên MT5 giao diện.

## Chạy nhiều preset

```bash
./tools/mt5/run_batch.sh \
  --from 2019.01.01 \
  --to 2022.12.31 \
  --deposit 5000 \
  outputs/presets/22_v11_pyramid_control_off.set \
  outputs/presets/23_v11_pyramid_add1_r0p20.set \
  outputs/presets/24_v11_pyramid_add1_r0p30.set
```

Batch chỉ compile một lần, sau đó chạy tuần tự từng preset. Chạy tuần tự giúp mỗi report và Journal gắn đúng một cấu hình, đồng thời tránh xung đột terminal hoặc local-agent port. Khi cần tối ưu hàng loạt tổ hợp tham số, dùng chế độ Optimization của MT5 trong một test riêng thay vì mở nhiều terminal dùng chung một Wine prefix.

