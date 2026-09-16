# Phase 3.1 Telemetry Coverage

`PHASE3_1_CANONICAL_TELEMETRY_STATUS`: `PASS_WITH_V63_HISTORICAL_COVERAGE_LIMITATION`

`MT5_TESTER_STATUS`: `PASS`

`MT5_EXECUTION_PARITY`: `PASS`
`EXECUTION_BEHAVIOR_DIFFERENCE_COUNT`: `0`

## Contract

- Old stream: `phase3-live-telemetry/1` / `EXECUTION_CANDIDATE`, diagnostic-only.
- New primary raw observation: `phase3-opportunity-observation/1`.
- New internal evidence: `phase3-canonical-opportunity/1`.
- Canonicalizer source of truth: `agent/data/normalization/canonical.py::canonical_opportunity_id`.
- Canonicalizer version: `canonical-opportunity/1`.
- Canonicalizer fingerprint: `0770ab50bf8509df0443468a9e2fbc0d1450b1c0cd167f56d426538f2b916892`.
- Candidate source head used for parity: `148dc44b18d3f8b9658ac83c593819b009eba8e5`.
- Evidence parent head before this reconciliation: `b152cd83269011c4af3bc9a2d5468783a2016efd`.

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
- Performance measurement: `NOT_MEASURED_NO_RUNTIME_STREAM`; no live or FORWARD runtime stream was generated. Tester telemetry was generated only for parity and is not used to claim write-latency or bytes-per-day metrics.

V26 authoritative fixtures are available. The V63 authoritative tester preset/config is available and was executed for execution parity. No authoritative V63 raw Phase 1 audit fixture is present in the current source inventory; therefore this report does not claim V63 historical coverage `PASS`.

## MT5 tester recovery and execution parity

The previous portable-terminal incident is retained as historical evidence in
`mt5_tester_diagnostic.md`. The portable runtime at
`E:\build-bot\outputs\build\mt5-latest\terminal64.exe` recorded no usable
Exness-MT5Real15 synchronization and tester-not-synchronized before automatic
testing, returning the `-1000012355` environment failure and creating no report.
It was not deleted or rewritten as a successful run.

The recovered environment was the installed, broker-synchronized terminal:

| Item | Result |
|---|---|
| Terminal | `D:\MetaTrader5\terminal64.exe`, build `5.0.0.6182` |
| MetaEditor | `D:\MetaTrader5\metaeditor64.exe`, build `5.0.0.6182` |
| Data directory | `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\03CEB46CA524FF6019F2D25A05B7513B` |
| Broker server | `Exness-MT5Real15` |
| Symbol / timeframe | `BTCUSD` / `H1` |
| Full range | `2023.04.01` → `2023.12.31` |
| Tester model | `4` — Every tick based on real ticks |
| Deposit / leverage | `5000 USD` / `1:10` |
| Execution mode / live trading | `0` / `AllowLiveTrading=0` |
| Session status | `READY_DURING_TEST_RUNS` |

The terminal log recorded broker authorization and terminal synchronization for
Exness-MT5Real15 before the sanity and full-range runs. The short sanity run on
`2023.04.01` → `2023.04.07` completed successfully and created a non-empty
64,724-byte report. All four full-range runs also completed successfully and
created non-empty reports:

| Run | Tester result | Report bytes | Signals | Orders | Deals |
|---|---|---:|---:|---:|---:|
| V26 baseline | `successfully finished` | 304,668 | 98 | 248 | 248 |
| V26 candidate | `successfully finished` | 305,320 | 98 | 248 | 248 |
| V63 baseline | `successfully finished` | 288,756 | 89 | 230 | 230 |
| V63 candidate | `successfully finished` | 289,408 | 89 | 230 | 230 |

The baseline was the original EA from main at
`6c3b9574f962f55bfb01e168f70eef0cad5e029c`; the candidate was built from
`148dc44b18d3f8b9658ac83c593819b009eba8e5`. The same terminal, symbol,
timeframe, dates, model, account settings, history and tester configuration
were used for both artifacts. Only the EA artifact and the V26/V63 preset
differed.

Candidate-only tester streams were created with schema
`phase3-opportunity-observation/1`: V26 had 735 rows / 1,025,318 bytes and V63
had 443 rows / 617,862 bytes. The observer was enabled by the tester contract;
these streams are telemetry evidence and are excluded from execution equality.

| Parity metric | V26 | V63 |
|---|---:|---:|
| Signal difference count | 0 | 0 |
| Order difference count | 0 | 0 |
| Execution behavior difference count | 0 | 0 |
| Parity status | `PASS` | `PASS` |

The report/deal comparator and independent ordered Tester-journal comparison
matched signal, order-performed, deal-performed, gate/diagnostic, position and
close behavior streams. Numeric tolerance is `1e-6` for price, lot, SL and TP
serialization only; it does not mask missing, extra, direction-changing or
gate-changing events.

This establishes V63 **execution parity**, not V63 **historical coverage**.
The latter remains `NOT_VERIFIED` until an authoritative V63 raw Phase 1 audit
fixture exists.

## Gate status and CI timing

- Historical adapter coverage: `PASS` (`3,618/3,618`, Phase 1 fingerprint unchanged).
- `MT5_TESTER_STATUS`: `PASS`.
- `MT5_EXECUTION_PARITY`: `PASS`.
- `SIGNAL_DIFFERENCE_COUNT`: `0`.
- `ORDER_DIFFERENCE_COUNT`: `0`.
- `EXECUTION_BEHAVIOR_DIFFERENCE_COUNT`: `0`.
- `MQL5_COMPILE`: `PASS_0_ERRORS_0_WARNINGS`.
- `EXECUTION_API_PATH_COUNT`: `0`.
- `LIVE_EXECUTION_ENABLED`: `NO`.
- `FORWARD_COLLECTION_STATUS`: `READY`.
- Authorization: not created.
- Task Scheduler: not installed or started.
- FORWARD run: not created.

The coverage JSON records
`CI_STATUS_AT_EVIDENCE_COMMIT_CREATION=PENDING_EXACT_HEAD_CI`. This is the
state at creation of the reconciliation commit, not a claim that CI failed.
After push, CI must be checked against the exact new commit and PR metadata
must be checked separately. Accordingly, `merge_ready=false` in this coverage
artifact means that the artifact itself does not self-authorize merge before
that post-commit verification; it is not an MT5 parity failure.

Sanitized evidence is limited to the coverage and parity reports. Raw terminal
logs, tester cache, runtime databases, broker-private data and HTML reports
remain outside Git. This PR stops before merge and before activation.
