# MT5 Execution Parity Report — Phase 3.1

## Gate result

- `MT5_TESTER_STATUS`: `UNAVAILABLE_TERMINAL_NOT_SYNCHRONIZED`
- `MT5_EXECUTION_PARITY`: `NOT_VERIFIED`
- `EXECUTION_BEHAVIOR_DIFFERENCE_COUNT`: `NOT_AVAILABLE`
- `MERGE_READY`: `NO`

The parity participants are defined but were not executed in this revision:

- Baseline: original EA at the `main` base revision, before the canonical telemetry
  observer changes.
- Candidate: current branch EA with the canonical opportunity observer.

Both are configured for the same terminal, symbol (`BTCUSD`), timeframe (`H1`), date
range (`2023-04-01` through `2023-12-31`), model (`4`, real ticks), execution mode,
deposit, currency, leverage, and version-specific inputs. The candidate compiled
with `0 errors, 0 warnings`, but the portable terminal could not synchronize with
`Exness-MT5Real15`; no valid tester report or behavioral diff exists yet.

## Historical prior gate

The repository's previous Phase 3.1 telemetry observer had a separate parity
result at candidate head `10a54dff750512ded8a6f89affc99ca7b4a270a5`, with zero
execution differences. That evidence remains recorded as historical context, but
it does not cover the canonical opportunity observer added by this branch. The
current branch therefore cannot inherit that PASS without a new compile and
same-environment run.

## Tester attempt and required comparison

The minimal sanity config was submitted twice. Both runs logged:

```text
Network: no connection to Exness-MT5Real15
Tester: not synchronized with trade server
Tester: terminal is not synchronized with the trade server before start automatic testing [1]
MQL5.community: authorization failed
```

No report file was created. The exact environment requirement is a synchronized
portable terminal session with the cached `BTCUSD/H1` history available; then rerun
sanity followed by V26 and V63 baseline/candidate runs.

The parity run must compare signal count/timestamps/side, order count/timestamps/
type, entry/lot/SL/TP, acceptance or rejection, gate decisions, and position
open/close behavior. Serialization-only numeric differences may use declared
floating tolerances; missing, extra, direction-changing, or gate-changing events
must never be tolerated.

Until that run produces `execution_behavior_difference_count = 0`, the status must
remain `MT5_EXECUTION_PARITY=NOT_VERIFIED` and `MERGE_READY=NO`.
