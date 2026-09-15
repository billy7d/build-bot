# MT5 execution parity report

## Required gate

The changed MQL5 source compiled successfully, but the required deterministic
baseline-versus-telemetry-enabled execution comparison is **not complete**.
Therefore:

```text
EXECUTION_PARITY_STATUS: NOT_RUN_INFRASTRUCTURE
EXECUTION_BEHAVIOR_DIFFERENCES: UNMEASURED
DO_NOT_MERGE: YES
```

The source diff is additive only (`190` lines added, no execution-source lines
removed). The new call is after the existing buy/sell request and has no return
value used by entry, exit, lot, SL, TP, risk, or gating logic. This is useful
source review evidence, but it is not a substitute for the PRD parity run.

## Controlled attempts

- `MetaEditor64.exe` with `E:\build-bot\outputs\build\mt5-v82-runtime\MQL5` include: `0 errors, 0 warnings`.
- `terminal64.exe` with the same deterministic tester configuration exited `-1000012355` before producing a report.
- `/portable` terminal remained without a tester report or usable log and was stopped after the bounded observation.
- Direct `metatester64.exe` exited `-1` without producing a report.

No report was compared, so the implementation does not claim `IDENTICAL` or a
zero behavior-difference result. A future gate must run the preserved baseline
EX5 and the telemetry-enabled EX5 over the same preset/window and compare
signal count/timestamps/side, order decisions, entry parameters, lot, SL, TP,
and trade gating before merge.
