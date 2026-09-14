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

## Trading Agent Phase 2

Phase 2 is an offline/research/shadow-only layer above the Phase 1 SQLite
dataset. It creates one canonical modeling sample per
`canonical_opportunity_id`, a closed-world Feature Store V1, chronological
TRAIN/VALIDATION/OOS splits, a train-only preprocessor, a rule-based regime
engine, a past-only historical similarity index, and interpretable baseline
scoring. It does not write orders or modify MT5/EA execution state.

From repository root:

```text
python -m agent.phase2 build-features
python -m agent.phase2 build-regimes
python -m agent.phase2 validate-similarity
python -m agent.phase2 train
python -m agent.phase2 evaluate
python -m agent.phase2 report
python -m agent.phase2 run-all
```

The default database is `data/trading_memory.db` and the reports are written
to `reports/trading_agent/phase2/`. The Phase 2 migration is additive at
`007_phase2_intelligence.sql`; raw datasets, SQLite files, Parquet exports,
similarity result caches and serialized model state remain untracked.

The Feature Store allowlist fails closed: unknown columns and outcome fields
such as `shadow_return_*`, `shadow_first_hit`, `actual_selected_*`,
`opportunity_diff_*`, `resolved`, `outcome_timestamp_utc` and
`incomplete_reason` are rejected rather than silently ignored. Imputation,
scaling, regime quantiles, calibration and model fitting record their scope
and never use OOS rows.
