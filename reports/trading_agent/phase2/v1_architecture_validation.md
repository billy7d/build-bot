# Phase 2 V1 Architecture Validation

```text
raw/audit data
      ↓
canonical opportunity (one sample per canonical_opportunity_id)
      ↓
feature store (closed allowlist, train-only preprocessing)
      ↓
rule-based regime engine
      ↓
historical similarity (expanding, past-only index)
      ↓
signal scoring (offline/shadow output)
      ↓
offline/shadow report
```

Validated negative path:

```text
signal scoring
      ↓
NO MT5 order path
```

Phase 2 does not import, call or mutate execution logic; it has no order writer or live bridge.

## Provenance

- Base SHA: `180e0e95e519ed532583c1c69fc7d358ab29f4f1`
- Generation SHA: `0a83f59723923ca52aec8b3fd1f34795f9d5be3b`
- Phase 1 dataset fingerprint: `NO_PHASE1_DATA`
- Feature Set: `feature-store/1`
- Split version: `phase2-split/1`
- Regime version: `regime/1`
- Similarity version: `similarity/1`
- Model version: `scoring/1`
- Random seed: `42`
- Config fingerprint: `79f3b3eb0ac4bb72d992fbc7121b26844884484cdeae45a478bfbec0a5a4c02b`
