# Trading Agent Phase 1 — Data Foundation Report

## Status

- Dataset: `TA-DATA-V1`
- Repository base SHA: `d8aa252ba9a5de89b9fb75c8bc1016750d3f2862`
- Dataset generation/implementation commit: `a834b18510d2b752f840bedd7a6e204c329ecb5d`
- Report capture commit: `cb150c60807ae3b705bb62ae066f818352b095dd`
- Dataset fingerprint: `2dc6dcd74928ed00923fd21f032ba0700f1c9c50459c9e0159872aa2045680ff`
- Quality: **PASS** ({'WARN': 3})
- SQLite migrations: `001, 002, 003, 004, 005, 006`
- SQLite foreign key check: **PASS**
- SQLite integrity check: **PASS**

## Source audit

- Inventory artifacts: `132`
- Source rows in registry: `126`
- Source status: `{'IMPORTED': 8, 'METADATA_ONLY': 118}`
- Supported strategy versions: `V26, V63`
- Audit layers: `V81, V82`
- Raw V82 status: **AVAILABLE**
- Missing/failed source counts are surfaced in `quality_report.json`; no aggregate V82 report was expanded into synthetic events.

## Coverage

- Episode date range UTC: `2023-01-01T00:00:00Z` → `2026-06-30T18:00:00Z`
- Audit observations / episode rows: `7236`
- Raw V82 observations: `3618`
- Unique underlying opportunities: `3618`
- Unique V81 / V82 opportunities: `3618 / 3618`
- Confirmed same underlying V81↔V82: `3618`; independent canonical opportunities: `0`; ambiguous: `0`
- Executed: `0`; non-executed candidates: `7236`
- Generic outcomes resolved/incomplete: `7196/40`
- Executions imported: `0`
- Opportunity contexts/outcomes: `3618/3618`
- Episode kinds: `{'BLOCKED_OPPORTUNITY': 5646, 'CONTROL_OPPORTUNITY': 795, 'FLAT_CANDIDATE': 795}`
- Sides: `{'LONG': 3214, 'SHORT': 4022}`
- Folds: `{'OOS': 3088, 'VALIDATION': 4148}`
- V82 event types: `{'BLOCKED_OPPOSITE': 580, 'BLOCKED_SAME_SIDE': 2243, 'LONG_ONLY': 360, 'SHORT_ONLY': 435}`
- Episode strategy coverage: `{'V26': 7236}`
- Episode audit coverage: `{'V81': 3618, 'V82': 3618}`

## Feature completeness

```json
{
  "ATR_percent": 100.0,
  "Active_context_percent": 39.0133,
  "Opportunity_outcome_percent": 49.7236,
  "RSI_percent": 100.0,
  "Regime_percent": 100.0,
  "Spread_percent": 100.0,
  "StdDev_percent": 50.0,
  "V81_unique_opportunities": 3618,
  "V82_shadow_outcome_percent": 49.7236,
  "V82_unique_opportunities": 3618,
  "Z-score_percent": 50.0,
  "audit_observations": 7236,
  "episodes": 7236,
  "unique_opportunities": 3618
}
```

Feature columns contain event-time values only. Outcome, counterfactual and opportunity-cost columns are stored separately.

## Required query coverage

The repository supports queries A-N plus O (unique canonical opportunity count) and P (all audit observations for one canonical id). `query_episodes(canonical_opportunity_id=...)`, `get_opportunity_observations(...)`, `count_unique_opportunities(...)` and `count_audit_observations(...)` preserve the distinction between opportunities and observations.

## Leakage and integrity

- Leakage status: **PASS**
- Lookahead violations: `0`
- Forbidden future fields are excluded from `episode_features` and raw feature JSON.
- V82 `opportunity_diff_*` is a label/outcome, never a feature.
- V82 `AMBIGUOUS` first-hit is preserved; incomplete rows remain in episode/outcome tables.

## Execution boundary

- V26 EA source and execution presets were not modified by Phase 1.
- No Python order sending, risk change, promotion, live deploy, V83 or execution gate is included.
- Missing V26/V63 trade history means executed-trade coverage is reported as absent rather than reconstructed.

## Known limitations

1. The raw V81 CSV has no embedded timezone field. The importer records `UTC` as `INFERRED` from the shared MT5 exporter contract and cross-checks V82 epoch IDs; this remains a provenance limitation and must be verified before cross-broker date comparisons.
2. This checkout contains V81/V82 shadow telemetry but no separate V26/V63 execution trade-history artifacts or backtests directory.
3. Parquet export uses an optional Arrow writer when available and a dependency-free uncompressed writer otherwise; SQLite remains the authoritative relational store.
4. Source files under ignored MT5 runtime copies are inventoried as duplicate paths or excluded runtime files; canonical raw V81/V82 paths are used for import.
5. Unknown metadata artifacts, inferred timezone metadata and duplicate runtime copies remain explicit warnings; they are not silently promoted to episode data.
