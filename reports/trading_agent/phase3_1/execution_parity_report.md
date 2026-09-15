# MT5 execution parity report

## Gate result

The deterministic MT5 Strategy Tester run recovered and the preserved baseline
was compared with the telemetry-enabled candidate over the same tester inputs.

```text
MT5_TESTER_STATUS: PASS
MT5_EXECUTION_PARITY: PASS
EXECUTION_BEHAVIOR_DIFFERENCE_COUNT: 0
SIGNAL_DIFFERENCE_COUNT: 0
ORDER_DIFFERENCE_COUNT: 0
DO_NOT_MERGE: YES (explicit STOP BEFORE MERGE instruction)
```

The source diff remains additive only (`190` lines added, no execution-source
lines removed). The telemetry call is after the existing buy/sell request and
its result is not read by entry, exit, lot, SL, TP, risk, or gating logic.

## Tester environment

- Intended portable runtime: `E:\build-bot\outputs\build\mt5-latest`.
- Terminal: `E:\build-bot\outputs\build\mt5-latest\terminal64.exe`, build `5.0.0.6182`.
- MetaEditor: `E:\build-bot\outputs\build\mt5-latest\MetaEditor64.exe`.
- Tester: `E:\build-bot\outputs\build\mt5-latest\metatester64.exe`.
- Tester-visible EA directory: `E:\build-bot\outputs\build\mt5-latest\MQL5\Experts\Advisors`.
- Tester logs: `E:\build-bot\outputs\build\mt5-latest\Tester\logs\20260915.log` and the local agent log.
- Report directory: `E:\build-bot\outputs\build\mt5-latest\reports\codex`.
- Symbol/timeframe: `BTCUSD`, `H1`.
- Date range: `2023.04.01 00:00` through `2023.12.31 00:00`.
- Model: `4` (Every tick based on real ticks); `ExecutionMode=0`.
- Optimization/forward/remote/cloud: `0` / `0` / disabled / disabled.
- Deposit/currency/leverage: `5000` / `USD` / `1:10`.
- Inputs: `79_v26_forward_demo.set`, copied to the tester-visible `MQL5\Profiles\Tester` directory.

Both runs used the same terminal, symbol, timeframe, historical cache, model,
execution mode, date range, deposit, currency, leverage, and preset. The only
participant change was the EA artifact and report filename.

## Participants and results

Baseline A is the exact original EA source at base commit
`820887cd11d7771741319f4fb8f8c2342bb342f0`, compiled as
`Phase31Baseline.ex5`. Candidate B is the current branch source at the reviewed
head `10a54dff750512ded8a6f89affc99ca7b4a270a5`, compiled as
`Phase31Telemetry.ex5`. SHA-256 identities and timestamps are recorded in
`execution_parity.json`.

The sanity run first loaded the baseline for `2023.04.01`–`2023.04.07` and
created a non-empty report. It recorded `522706` real ticks, `144` bars, and
`6` total trades. It is a tester-health result, not the parity result.

The official runs both completed successfully with `100% real ticks`,
`30904792` ticks, and `6576` bars:

| Metric | Baseline A | Candidate B | Difference |
| --- | ---: | ---: | ---: |
| Report total trades | 150 | 150 | 0 |
| Closed cycles | 94 | 94 | 0 |
| Report deal sequence | 248 | 248 | 0 |
| Orders | 248 | 248 | 0 |
| Accepted entry signal trace (time/side/comment) | 98 | 98 | 0 |
| Filled order states | 248 | 248 | 0 |
| Total net profit | 113.56 | 113.56 | 0 |
| Final balance | 5113.56 | 5113.56 | 0 |

The existing `tools/mt5/compare_execution_regression.py` returned
`equal=true`, with a complete 248-deal sequence and no mismatches. The order
table comparison also matched open/order timestamps, side/type, volume,
market-price field, SL, TP, state, and comment. Diagnostic `OnTester` groups
for the official baseline and candidate matched exactly, including core trade,
side, and gate-counter fields. Numeric comparisons used `1e-6`; timestamps,
symbol, direction, state, comments, and event ordering remained exact strings.

## Recovery root cause

The original `-1000012355` was not evidence of an MQL5 trading-logic defect.
The startup log showed the terminal could not connect to
`Exness-MT5Real15`, reported that the tester was not synchronized with the
trade server, and then produced no report. The old configuration also started
in January 2023 while the selected portable runtime had local BTCUSD tick
files beginning in April, and the required preset/artifact deployment was not
present at the tester-visible paths. The evidence-supported classification is:

```text
ENVIRONMENT_ERROR + TESTER_CONFIG_ERROR + SYMBOL_DATA_ERROR + EX5_PATH_ERROR
```

Recovery consisted only of selecting the explicit portable runtime, waiting for
normal terminal authorization/synchronization, deploying the exact baseline
and candidate EX5 artifacts under `MQL5\Experts\Advisors`, copying the existing
preset, and using the first fully cached deterministic date range. No strategy,
model, bundle, cutoff, risk, lot, SL/TP, gate, or forward-authorization logic
was changed. Full diagnostic evidence is in `mt5_tester_diagnostic.md`.

## Artifact handling

The two HTML reports and raw terminal/agent logs remain runtime evidence only;
they are not committed. The repository contains sanitized metadata and counts
in `execution_parity.json`, with no runtime database, tester cache, or broker
private data.
