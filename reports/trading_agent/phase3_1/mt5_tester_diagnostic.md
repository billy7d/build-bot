# MT5 Tester Diagnostic — Phase 3.1 Canonical Telemetry

## Recovered status

```text
MT5_TESTER_STATUS: PASS
MT5_SESSION_STATUS: READY_DURING_TEST_RUNS
MT5_EXECUTION_PARITY: PASS
EXECUTION_BEHAVIOR_DIFFERENCE_COUNT: 0
```

## Root cause of `-1000012355`

The repository portable runtime at
`E:\build-bot\outputs\build\mt5-latest\terminal64.exe` was build `6182`,
but its current log repeatedly recorded `no connection to
Exness-MT5Real15`, authentication failure and `Tester not synchronized with
trade server` before automatic testing. It created no valid report. This was
classified as `ENVIRONMENT_ERROR / ACCOUNT_TERMINAL_STATE_ERROR`, not as a
MQL5 trading-logic defect.

The working environment was the installed build:

```text
terminal: D:\MetaTrader5\terminal64.exe
version: 5.0.0.6182
MetaEditor: D:\MetaTrader5\metaeditor64.exe, build 6182
data: C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\03CEB46CA524FF6019F2D25A05B7513B
server: Exness-MT5Real15
```

The selected terminal log recorded broker authorization and synchronization at
13:19:45, 13:25:02/03, 13:28:20, 13:35:41 and 13:38:01 on 2026-09-16. These
events were read from the terminal log; GUI title/account selection was not
used as proof.

## Sanity test

The short sanity test used BTCUSD/H1, 2023.04.01–2023.04.07, model 4,
`AllowLiveTrading=0`, deposit 5000 USD and leverage 1:10. It completed with
`successfully finished`, generated 144 H1 bars, and created this non-empty
report:

```text
C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\03CEB46CA524FF6019F2D25A05B7513B\reports\codex\phase3_d_installed_sanity.html
bytes: 64724
```

## Full-range tester evidence

All four runs used the same terminal, data directory, BTCUSD symbol, H1
timeframe, 2023.04.01–2023.12.31 range, real-tick model 4, execution mode 0,
deposit, currency, leverage, and live-trading-disabled contract. Only the
baseline/candidate EX5 and their V26/V63 preset were different.

| Run | Tester result | Duration | Report bytes |
|---|---|---:|---:|
| V26 baseline | successfully finished | 0:02:25.455 | 304668 |
| V26 candidate | successfully finished | 0:02:26.699 | 305320 |
| V63 baseline | successfully finished | 0:01:46.068 | 288756 |
| V63 candidate | successfully finished | 0:01:47.780 | 289408 |

Each full run logged `BTCUSD,H1: 6576 bars generated` and environment
synchronization before the test result. The four reports are external runtime
artifacts and are not committed.

## Parity evidence

```text
V26 signals: 98 vs 98; SIGNAL_DIFFERENCE_COUNT=0
V26 orders: 248 vs 248; ORDER_DIFFERENCE_COUNT=0
V26 deals: 248 vs 248

V63 signals: 89 vs 89; SIGNAL_DIFFERENCE_COUNT=0
V63 orders: 230 vs 230; ORDER_DIFFERENCE_COUNT=0
V63 deals: 230 vs 230

EXECUTION_BEHAVIOR_DIFFERENCE_COUNT=0
```

The report/deal comparator and the independent ordered Tester-journal stream
comparison both matched. Signal events were accepted base/pyramid entry events;
order and deal counts were taken from `order performed` and `deal performed`
events. Gate/diagnostic, position, close and execution event streams were also
equal. No differing event exists to report.

Floating serialization tolerance was `1e-6` for price, lot, SL and TP only. It
does not mask missing/extra events, direction changes or gate decisions.

## Candidate observer confirmation

The candidate V26/V63 presets explicitly enabled both canonical observer inputs:

```text
ExportPhase3OpportunityJsonl=true
ExportPhase3OpportunityInTester=true
```

The tester produced candidate-only JSONL under FILE_COMMON with schema
`phase3-opportunity-observation/1` (735 V26 rows and 443 V63 rows). Those files
are telemetry evidence, not execution evidence, and were excluded from the
execution equality comparator.

## Safety boundary

```text
MQL5_COMPILE: PASS (0 errors, 0 warnings)
EXECUTION_API_PATH_COUNT: 0
LIVE_EXECUTION_ENABLED: NO
EXECUTION_AUTHORITY: NONE
TRADE_CONTROL_AUTHORITY: NONE
FORWARD_COLLECTION_STATUS: READY
FORWARD_AUTHORIZATION: NONE / NOT_CREATED
TASK_SCHEDULER: NOT_INSTALLED
FORWARD_RUN: NONE
```

No source trading/canonical telemetry change was made during environment
recovery. Final CI and PR mergeability must be checked on the new evidence
commit, then stop before merge.
