# Máy 1 — Triển khai forward resilience và campaign (2026-10-06)

Dành cho agent trên máy 1 **sau khi** PR `fix/phase3-forward-resilience-campaign` được operator merge vào
`main`. Không làm gì trong tài liệu này trước khi merge.

## Thay đổi

| | Trước | Sau |
|---|---|---|
| Lỗi ghi `heartbeat.json` | Run FAILED, mất dữ liệu tới khi có người khởi động lại | Ghi health event `HEARTBEAT_WRITE_FAILED`, collector chạy tiếp |
| Lý do run FAILED | Không lưu (lần V26 ngày 03/10 mất lý do) | Health event `RUN_FAILED` có loại lỗi và thông điệp; `status-runtime` có `last_failure` |
| Đếm mẫu forward | Theo từng run, về 0 sau mỗi sự cố | Theo campaign: gộp mọi run cùng bundle, khử trùng theo `canonical_opportunity_id` |
| Coverage | Không đo | Bảng liveness mỗi run; `campaign-status` liệt kê khoảng trống |

Migration `010` là additive: chỉ thêm bảng, không sửa dữ liệu cũ. Nó tự chạy khi collector mở DB.

## Quy trình (lặp lại cho V26 và V63, mỗi hệ thống một runtime root)

Đường dẫn dưới đây theo máy 1 hiện tại: V26 `D:\Trading\build-bot-runtime\phase3`, V63
`D:\Trading\build-bot-runtime\phase3-v63`.

1. **Dừng collector đang chạy** (không ảnh hưởng MT5):

   ```powershell
   .\scripts\phase3\stop_forward_task.ps1            # V26; với V63 dùng -TaskName BuildBot-Phase3-Forward-V63
   py -3 -m agent.phase3 stop-forward --runtime-config <forward.json> --run-id <run_id hiện tại>
   ```

   Chờ `status-runtime --json` báo `STOPPED`. Run cũ ở trạng thái `STOPPED` (không phải FAILED) vẫn được
   tính vào campaign.

2. **Cập nhật checkout runtime** khi cả hai collector đã dừng:

   ```powershell
   git -C D:\Trading\buildbot pull --ff-only
   git -C D:\Trading\buildbot status --short --branch     # tracked tree sạch
   ```

3. **Sao lưu runtime DB** trước khi migration chạy, bằng cách copy (không di chuyển, không xóa):
   `db\phase3-forward.sqlite` sang `evidence\pre-010-<yyyyMMdd>.sqlite`.

4. **Thêm `campaign_id` vào `forward.json`.** Tên đề xuất:
   - V26: `"campaign_id": "v26-bundle577e-c1"`
   - V63: `"campaign_id": "v63-bundle577e-c1"`

5. **Khai báo campaign.** `window_start_utc` cố định là `2026-10-02T00:00:00Z` cho cả hai, để mọi run thật
   từ ngày kích hoạt đều thuộc campaign theo quy tắc, không chọn tay:

   ```powershell
   py -3 -m agent.phase3 campaign-declare --runtime-config <forward.json> --window-start-utc 2026-10-02T00:00:00Z
   py -3 -m agent.phase3 campaign-status --runtime-config <forward.json>
   ```

   Kỳ vọng: mọi run FORWARD từ 02/10 có trong `member_run_ids`. Run tạo trước migration có
   `coverage_basis=ESTIMATED_PRE_LIVENESS`, tức coverage được ước lượng thấp; điều này được chấp nhận.

6. **Gate evidence và authorization mới** tại SHA mới (như §7–§8 của handoff 01/10): unit test,
   replay/parity, smoke, `prepare-forward`.

7. **Start run mới.** `start-forward` tự từ chối nếu campaign chưa được khai báo, và tự gắn run mới vào
   campaign. Sau đó bật lại task.

8. **Kiểm tra:**

   ```powershell
   py -3 -m agent.phase3 status-runtime --runtime-config <forward.json> --json
   ```

   Kỳ vọng: `RUNNING`, `CONNECTED`, `campaign.campaign_id` đúng, `last_failure=null` cho run mới.

## Báo cáo về máy 2

Cập nhật `machine1_forward_activation_20261001.md` trên branch ops với: SHA mới, authorization và run id
mới, output `campaign-status` (chỉ phần membership, sample count và gaps), và các sai lệch.

**Không** chạy `evaluate-campaign` và không đưa metric dự đoán vào báo cáo: outcome forward chỉ được mở
theo lịch đánh giá cố định (Phase 4 design §6.4).

## Điều kiện dừng

- `campaign-declare` từ chối hoặc có run trong `excluded` (sai canonicalizer): dừng, báo operator.
- Migration lỗi hoặc `integrity_check` khác `ok`: khôi phục từ bản sao ở bước 3, dừng, báo.
- Các điều kiện dừng của handoff 01/10 vẫn áp dụng.
