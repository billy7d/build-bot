# MT5 Execution Parity Report — Phase 3.1

## Gate result

- `MT5_TESTER_STATUS`: `UNAVAILABLE_TERMINAL_NOT_SYNCHRONIZED`
- `MT5_EXECUTION_PARITY`: `NOT_VERIFIED`
- `EXECUTION_BEHAVIOR_DIFFERENCE_COUNT`: `NOT_AVAILABLE`
- `MERGE_READY`: `NO`

Base: `6c3b9574f962f55bfb01e168f70eef0cad5e029c`

Candidate branch head at the latest evidence update: `646ab9738557ef6e4bf92958764bad1a6965e374`

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

The minimal sanity config was submitted seven times. The latest `/portable` run used the
audited config with explicit Login/Server, `AllowLiveTrading=0`, and MT5-native
single-separator paths. The earlier three runs logged:

```text
Network: no connection to Exness-MT5Real15
Tester: not synchronized with trade server
Tester: terminal is not synchronized with the trade server before start automatic testing [1]
MQL5.community: authorization failed
```

No report file was created. A fresh fourth invocation after the manual-login
report still logged `MQL5.community authorization failed` and produced no
`authorized` or `terminal synchronized` event in the portable log. The exact
environment requirement is a synchronized
portable terminal session with the cached `BTCUSD/H1` history available; then rerun
sanity followed by V26 and V63 baseline/candidate runs. The preceding tester
startup logged `no connection to Exness-MT5Real15` and `terminal is not
synchronized with the trade server`; the fresh fourth invocation logged
`authorization failed`. The sixth `/portable` invocation at 11:56 produced the
same `no connection`, `authorization failed`, and `not synchronized` sequence
before automatic testing. After a manual login and full exit, the seventh
`/portable` invocation at 12:10 reproduced the same sequence. This remains an
environment/account-state blocker rather than a comparator or strategy result.

The parity run must compare signal count/timestamps/side, order count/timestamps/
type, entry/lot/SL/TP, acceptance or rejection, gate decisions, and position
open/close behavior. Serialization-only numeric differences may use declared
floating tolerances; missing, extra, direction-changing, or gate-changing events
must never be tolerated.

Until that run produces `execution_behavior_difference_count = 0`, the status must
remain `MT5_EXECUTION_PARITY=NOT_VERIFIED` and `MERGE_READY=NO`.
