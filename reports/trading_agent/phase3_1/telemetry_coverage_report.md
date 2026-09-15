# Phase 3.1 Telemetry Coverage

`PHASE3_1_CANONICAL_TELEMETRY_STATUS`: `BLOCKED_ON_MT5_TESTER_SYNCHRONIZATION`

## Contract

- Old stream: `phase3-live-telemetry/1` / `EXECUTION_CANDIDATE`, diagnostic-only.
- New primary raw observation: `phase3-opportunity-observation/1`.
- New internal evidence: `phase3-canonical-opportunity/1`.
- Canonicalizer source of truth: `agent/data/normalization/canonical.py::canonical_opportunity_id`.
- Canonicalizer version: `canonical-opportunity/1`.
- Canonicalizer fingerprint: `0770ab50bf8509df0443468a9e2fbc0d1450b1c0cd167f56d426538f2b916892`.

Phase 1 fingerprint before/after remains:

`2dc6dcd74928ed00923fd21f032ba0700f1c9c50459c9e0159872aa2045680ff`

The frozen bundle and cutoff remain unchanged:

- Bundle: `p3-bundle-577e5dfd0702c52c8f5318063703dd616a633704444ba5371e1c74e6dc080c6a`
- Cutoff: `2023-12-30T08:00:00Z`

## Deterministic historical coverage

Validation period: `2023-01-01T00:00:00Z` → `2026-06-30T18:00:00Z`.

| Metric | Result |
|---|---:|
| Raw authoritative V81/V82 observations | 7,236 |
| Expected canonical opportunities | 3,618 |
| Actual canonical opportunities | 3,618 |
| Missing | 0 |
| Unexpected | 0 |
| Raw overlap collapse | 3,618 |
| Duplicate canonical predictions | 0 |
| Precision | 1.0 |
| Recall | 1.0 |

The actual set is produced by deterministic replay of the authoritative Phase 1 V81/V82 artifacts through the new raw-observation adapter and the existing Phase 1 canonicalizer. It does not claim that a FORWARD source was activated; `FORWARD_RUN_ID=NOT_CREATED`.

## Coverage rates

- New canonical rate: calculated from the unique canonical IDs per month in the full historical window; the complete machine-readable monthly series is in `telemetry_coverage.json`.
- Resolved labels: 3,598 unique canonical opportunities, 85.66666666666667/month over the resolved historical window.
- Estimated time to 500 resolved labels: 5.836575875486381 months.
- Old execution-candidate monthly rate: `NOT_AVAILABLE`; no saved old primary stream was found, so no multiplier or old ETA is invented.
- Performance measurement: `NOT_MEASURED_NO_RUNTIME_STREAM`; no live/tester stream was generated, so write-latency and bytes-per-day metrics are not invented.

V26 authoritative fixtures are available. No authoritative V63 audit fixture is present in the current Phase 1 source inventory; this remains a separate evidence blocker for V63-specific coverage/parity and is not fabricated.

## Gate status at this report revision

- Historical adapter coverage: `PASS`.
- `MT5_TESTER_STATUS`: `UNAVAILABLE_TERMINAL_NOT_SYNCHRONIZED`.
- `MQL5_COMPILE`: `PASS_0_ERRORS_0_WARNINGS`.
- `MT5_EXECUTION_PARITY`: `NOT_VERIFIED`.
- `EXECUTION_BEHAVIOR_DIFFERENCE_COUNT`: `NOT_AVAILABLE` because the tester did not produce a report.
- `READY_FOR_PHASE4=NO`.
- `LIVE_EXECUTION_ENABLED=NO`.
- `FORWARD_COLLECTION_STATUS=READY`.
- No authorization was created.
- No Task Scheduler task was installed or started.
- No FORWARD run or live activation was performed.

The current MetaEditor run used `D:\MetaTrader5\metaeditor64.exe`, build
`5.0.0.6182`, with `outputs/build/mt5-v82-runtime/MQL5/Include`; it produced a
303,546-byte tester-visible candidate EX5 with `0 errors, 0 warnings`. The portable
tester used build `5.0.0.6182` from `outputs/build/mt5-latest`, but both sanity
attempts logged that the terminal was not synchronized with the trade server and
created no report. See `mt5_tester_diagnostic.md` for the exact log evidence.

This PR stops before merge and before activation.
