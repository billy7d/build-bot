# V81 ↔ V82 Opportunity Overlap Audit

## Counts

| Metric | Count |
| --- | ---: |
| V81 audit observations | `3618` |
| V82 audit observations | `3618` |
| Total audit observations | `7236` |
| Unique V81 opportunities | `3618` |
| Unique V82 opportunities | `3618` |
| Exact timestamp + side matches | `0` |
| Timestamp-only matches | `14` |
| Timestamp + side + entry matches | `0` |
| Raw event_id matches | `0` |
| Confirmed same underlying opportunities | `3618` |
| Confirmed independent opportunities | `0` |
| Ambiguous matches | `0` |
| Unexpected canonical collisions | `0` |

## Interpretation

The database contains audit observations, not automatically independent opportunities. The canonical linkage currently confirms **3618** V81↔V82 observation pairs as the same underlying opportunity. Therefore the combined unique opportunity count is not the sum of the two audit row counts.

The V81 source timestamp remains preserved as `source_time` with its existing `UTC / INFERRED` provenance. The observed one-hour offset is used only to explain the cross-audit match; it does not rewrite raw timestamps or timezone metadata.

## Methodology

- Exact timestamp + side: Giao của (timestamp_utc, side) sau normalization, không bù giờ.
- Timestamp-only: Giao của timestamp_utc distinct, không dùng side hay price.
- Timestamp + side + entry: Giao của (timestamp_utc, side, entry_candidate).
- Canonical match: Giao của canonical_opportunity_id; mỗi nhóm được kiểm tra identity key và một row mỗi audit.
- Canonical identity fields: `strategy_version, symbol, timeframe, candidate_semantic, side, entry_candidate, stop_candidate, risk_distance`
- Excluded from identity: `audit_version, source path, parser version, database id, raw_event_id`
- Timestamp reconciliation: V81 timestamp_utc lớn hơn V82 đúng 1 giờ ở mọi nhóm confirmed; chỉ dùng cho audit linkage, không rewrite source_time/source_timezone/raw fields.
- Independence rule: Một episode/audit observation không mặc định là một opportunity độc lập; chỉ canonical id khác mới là opportunity khác.

## Field-by-field comparison

- Symbol exact matches: `3618`; timeframe: `3618`; side: `3618`.
- Candidate semantic + entry + stop + risk exact matches: `3618`.
- Common signal-context exact matches: `{'composite_regime_score->composite_regime_score': 3618, 'd1_regime_score->d1_regime_score': 3618, 'entry_atr_pct->entry_atr_pct': 35, 'entry_rsi->shadow_entry_rsi': 32, 'entry_spread_r->entry_spread_r': 40, 'h4_regime_score->h4_regime_score': 3618}`. Context fields not equal remain audit-specific source fields and were not silently overwritten.
- `setup_generation` present: V81 `0`, V82 `3618`; setup generation is not used as a join key because V81 does not report the same field.
- Timestamp không đưa vào hash canonical vì raw V81/V82 lệch một giờ; candidate identity tuple phải unique trên dataset và được quality gate kiểm tra collision.

## Collision and provenance checks

- Same-audit duplicate canonical groups: `0`.
- Unexpected canonical identity collisions: `0`. A two-row V81/V82 group is intentional only when it has one row from each audit and the proven timestamp reconciliation.
- Timestamp offsets among confirmed pairs (hours): `{'1': 3618}`.
- Raw `event_id` is retained per source as `raw_event_id`; it is not used as a cross-audit join key because V81 and V82 expose different identity formats.

## Sample linked pairs

```json
[
  {
    "canonical_opportunity_id": "opp-0006e6e5394398b6f8e39a3fea8d3fea599c9e29052b06a16b4b4d5c5ffb45af",
    "v81_episode_id": "BTCUSD-H1-20230105T120000Z-V26-V81-LONG-BLOCKED-OPPORTUNITY-0001",
    "v81_raw_event_id": "17",
    "v81_timestamp_utc": "2023-01-05T12:00:00Z",
    "v82_episode_id": "BTCUSD-H1-20230105T110000Z-V26-V82-LONG-BLOCKED-OPPORTUNITY-0001",
    "v82_raw_event_id": "1672916400_G_10_LONG_BLOCKED_SAME_SIDE",
    "v82_timestamp_utc": "2023-01-05T11:00:00Z"
  },
  {
    "canonical_opportunity_id": "opp-000d77e877f170c808d4bb66a6f5b4e8c6cb69b40e26766aa2a02b6e4427270c",
    "v81_episode_id": "BTCUSD-H1-20260325T090000Z-V26-V81-LONG-BLOCKED-OPPORTUNITY-0001",
    "v81_raw_event_id": "230",
    "v81_timestamp_utc": "2026-03-25T09:00:00Z",
    "v82_episode_id": "BTCUSD-H1-20260325T080000Z-V26-V82-LONG-BLOCKED-OPPORTUNITY-0001",
    "v82_raw_event_id": "1774425600_G_82_LONG_BLOCKED_SAME_SIDE",
    "v82_timestamp_utc": "2026-03-25T08:00:00Z"
  },
  {
    "canonical_opportunity_id": "opp-0017545e34e8e548b1519f8414cf345e6cf53b88232e74d58ecfb7fb61ed6df3",
    "v81_episode_id": "BTCUSD-H1-20260219T120000Z-V26-V81-SHORT-BLOCKED-OPPORTUNITY-0001",
    "v81_raw_event_id": "138",
    "v81_timestamp_utc": "2026-02-19T12:00:00Z",
    "v82_episode_id": "BTCUSD-H1-20260219T110000Z-V26-V82-SHORT-BLOCKED-OPPORTUNITY-0001",
    "v82_raw_event_id": "1771498800_G_52_SHORT_BLOCKED_SAME_SIDE",
    "v82_timestamp_utc": "2026-02-19T11:00:00Z"
  }
]
```

Phase 2 export must carry `canonical_opportunity_id` and must not sample two audit observations with the same canonical id as independent training opportunities.
