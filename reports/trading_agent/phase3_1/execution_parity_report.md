# MT5 Execution Parity Report — Phase 3.1 Canonical Telemetry

## Gate result

```text
MT5_TESTER_STATUS: PASS
MT5_EXECUTION_PARITY: PASS
EXECUTION_BEHAVIOR_DIFFERENCE_COUNT: 0
```

The prior `-1000012355` blocker was an environment/session-state failure in the
repository portable runtime. It was recovered by using the installed MT5 build
6182 and its broker-synchronized data directory. No trading source, model,
bundle, cutoff, risk, gate, or canonical telemetry logic was changed for this
recovery.

The exact candidate source head tested was
`148dc44b18d3f8b9658ac83c593819b009eba8e5`; the baseline was main at
`6c3b9574f962f55bfb01e168f70eef0cad5e029c`.

## Tester environment

| Item | Value |
|---|---|
| Terminal | `D:\MetaTrader5\terminal64.exe` |
| Terminal build | `5.0.0.6182` |
| MetaEditor | `D:\MetaTrader5\metaeditor64.exe` build `6182` |
| Data directory | `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\03CEB46CA524FF6019F2D25A05B7513B` |
| Broker server | `Exness-MT5Real15` |
| Symbol | `BTCUSD` |
| Timeframe | `H1` |
| Date range | `2023.04.01` through `2023.12.31` |
| Tester model | `4` — Every tick based on real ticks |
| Deposit / leverage | `5000 USD` / `1:10` |
| Execution mode | `0` |
| AllowLiveTrading | `0` |

The terminal log recorded `authorized on Exness-MT5Real15` and `terminal
synchronized with Exness Technologies Ltd` before every sanity, baseline and
candidate run. The Tester log recorded `BTCUSD,H1`, `6576 bars generated`,
environment synchronization, and `successfully finished` for every full-range
run.

## Recovery and sanity evidence

The old portable attempt was classified as
`ENVIRONMENT_ERROR / ACCOUNT_TERMINAL_STATE_ERROR`: its log contained no
connection/authentication failure and tester-not-synchronized messages, and it
created no report. The installed terminal then passed a short sanity run on
`BTCUSD/H1`, `2023.04.01` through `2023.04.07`, model `4`.

Sanity report:

```text
path: C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\03CEB46CA524FF6019F2D25A05B7513B\reports\codex\phase3_d_installed_sanity.html
bytes: 64724
tester result: successfully finished
test duration: 0:00:01.347
```

The report was non-empty and timestamped by the current sanity run. No report
was fabricated.

## Baseline and candidate artifacts

| Artifact | Source revision | EX5 size | SHA-256 |
|---|---|---:|---|
| Baseline | `6c3b9574f962f55bfb01e168f70eef0cad5e029c` | 277194 | `6671A56F2FB2C12B2ED4871EEFC9C1C476730094EEEC789EC1848CAA9D52715E` |
| Candidate | `148dc44b18d3f8b9658ac83c593819b009eba8e5` | 305704 | `A4E77D4A16EE17B5327DFDBA8B5D8F503413BB419C61082B93A92A8FD63565BE` |

The candidate V26 and V63 `.set` files had
`ExportPhase3OpportunityJsonl=true` and
`ExportPhase3OpportunityInTester=true`. Candidate-only JSONL was validated as
`phase3-opportunity-observation/1` with 735 V26 rows and 443 V63 rows. This is
observer evidence only; it is not used to make execution parity pass.

## Same-environment parity results

| Variant | Baseline / candidate total trades | Baseline / candidate deal events | Baseline / candidate signal events | Baseline / candidate order events | Signal diff | Order diff | Execution diff |
|---|---:|---:|---:|---:|---:|---:|---:|
| V26 | 150 / 150 | 248 / 248 | 98 / 98 | 248 / 248 | 0 | 0 | 0 |
| V63 | 141 / 141 | 230 / 230 | 89 / 89 | 230 / 230 | 0 | 0 | 0 |

The existing `compare_execution_regression.py` comparator returned `equal=true`
for both V26 and V63, with report metrics and ordered deal sequences equal and
no mismatches. The independent Tester-journal stream comparison also found
equal signal, order-performed, deal-performed, gate/diagnostic, position and
close behavior streams. The first differing trading event is therefore none.

The numeric tolerances were `price=1e-6`, `lot=1e-6`, `SL=1e-6`, and `TP=1e-6`.
They apply only to floating-point serialization. Missing, extra, direction-
changing, or gate-changing events were not tolerated.

Reports created by the tester were checked as external runtime artifacts:

```text
V26 baseline: 304668 bytes, successfully finished in 0:02:25.455
V26 candidate: 305320 bytes, successfully finished in 0:02:26.699
V63 baseline: 288756 bytes, successfully finished in 0:01:46.068
V63 candidate: 289408 bytes, successfully finished in 0:01:47.780
```

Raw HTML reports, terminal logs, agent logs, common-files telemetry and tester
cache remain outside Git. Only sanitized lightweight evidence is intended for
the repository.

## Safety and remaining release gate

```text
MQL5_COMPILE: PASS (0 errors, 0 warnings)
EXECUTION_API_PATH_COUNT: 0
LIVE_EXECUTION_ENABLED: NO
EXECUTION_AUTHORITY: NONE
TRADE_CONTROL_AUTHORITY: NONE
FORWARD_COLLECTION_STATUS: READY
FORWARD_AUTHORIZATION: NOT_CREATED
TASK_SCHEDULER: NOT_INSTALLED
FORWARD_RUN: NONE
```

The evidence establishes `MT5_EXECUTION_PARITY=PASS`. Final `MERGE_READY` is
subject to rerunning the repository gates on the evidence commit, CI on that
exact new PR head, and a fresh PR mergeability/behind-main check. The process
stops before merge.
