# Trading Agent Phase 2

Offline / research / shadow intelligence only.

PHASE2_ENGINEERING_STATUS: PASS
FEATURE_STORE_READY: YES
REGIME_ENGINE_READY: YES
SIMILARITY_ENGINE_READY: YES
SIGNAL_SCORING_READY: YES
LEAKAGE_STATUS: PASS
REPRODUCIBILITY_STATUS: PASS
TRAIN_COUNT: 1002
VALIDATION_COUNT: 1072
OOS_COUNT: 1544
PREDICTIVE_EDGE_STATUS: NOT_DEMONSTRATED
LIVE_EXECUTION_ENABLED: NO
READY_FOR_PHASE3: YES

## Provenance

- Base SHA: `180e0e95e519ed532583c1c69fc7d358ab29f4f1`
- Generation SHA: `ae33133d09cc04b4acaeba4422791382957cc999`
- Phase 1 dataset fingerprint: `2dc6dcd74928ed00923fd21f032ba0700f1c9c50459c9e0159872aa2045680ff`
- Input dataset status: `AVAILABLE`
- Canonical opportunities: `3618`
- Audit observations: `7236`
- Feature Set: `feature-store/1`
- Registered features: `29`

## Engineering checks

```json
{
  "canonical_dedup": true,
  "canonical_overlap": true,
  "feature_leakage": true,
  "phase1_data_available": true,
  "phase1_lookahead": true,
  "regime_pipeline": true,
  "reproducibility_fingerprints": true,
  "scoring_pipeline": true,
  "similarity_temporal": true,
  "sqlite_foreign_keys": true,
  "sqlite_integrity": true,
  "temporal_split": true
}
```

Signal scoring emits opinion/status metadata only. No execution command, order, position, lot, SL, TP, pyramid or risk-management output is implemented.
If input dataset status is `MISSING_PHASE1_DATA`, this checkout contains no Phase 1 SQLite/raw observations; the pipeline intentionally reports FAIL/INSUFFICIENT_DATA instead of reconstructing them.
