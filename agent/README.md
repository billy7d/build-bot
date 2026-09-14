# Trading Memory Phase 1

Các CLI chạy offline từ thư mục gốc repository:

```text
python -m agent.data.inventory
python -m agent.data.import_all
python -m agent.evaluation.data_quality
python -m agent.memory.parquet export
```

Pipeline giữ raw provenance, chuẩn hóa V81/V82 thành Trading Episode, tách
feature khỏi outcome/counterfactual, chạy leakage/quality gates và export
SQLite/Parquet. DB, raw data và Parquet không được commit.

`trading_episodes` là audit observations. `canonical_opportunity_id` dùng
identity chung để đếm underlying opportunities và phải được giữ trong export;
hai observation có cùng canonical id không được lấy làm hai mẫu độc lập ở
Phase 2. Query `O` đếm unique canonical opportunities và query `P` trả toàn bộ
observation của một canonical id.

`V26`/`V63` là execution strategy; `V81`/`V82` là audit layer. Data foundation
không gửi lệnh, không thay EA/risk/gate và không tạo synthetic V82 events.

Manifest provenance giữ `repository_base_sha`, `dataset_generation_commit`,
`report_capture_commit` và `dataset_fingerprint` với semantics độc lập với PR.
The current PR head is intentionally not embedded in `dataset_manifest.json`
because it is mutable PR metadata rather than dataset provenance.
