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

`V26`/`V63` là execution strategy; `V81`/`V82` là audit layer. Data foundation
không gửi lệnh, không thay EA/risk/gate và không tạo synthetic V82 events.
