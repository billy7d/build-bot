# MT5 Tester Diagnostic — Phase 3.1 Canonical Telemetry

## Result

- `MT5_TESTER_STATUS`: `UNAVAILABLE_TERMINAL_NOT_SYNCHRONIZED`
- `MT5_EXECUTION_PARITY`: `NOT_VERIFIED`
- `MERGE_READY`: `NO`
- `LIVE_EXECUTION_ENABLED`: `NO`
- `FORWARD_COLLECTION_STATUS`: `READY`

The tester sanity run was attempted twice and the original-vs-telemetry parity run
was not started after both attempts failed to synchronize. The updated EA did
compile into a new tester-visible EX5, so the remaining failure is the terminal
session/data synchronization gate rather than an MQL compile failure.

## Environment observed

| Item | Observed value |
|---|---|
| Tester terminal | `E:\build-bot\outputs\build\mt5-latest\terminal64.exe` |
| Terminal build | `5.0.0.6182` |
| MetaEditor | `D:\MetaTrader5\metaeditor64.exe` |
| MetaEditor build | `5.0.0.6182` |
| Source | `outputs/Mentor_RSI_MTF_v1.mq5` |
| Include root used | `outputs/build/mt5-v82-runtime/MQL5/Include` |
| Candidate EX5 | `outputs/build/mt5-latest/MQL5/Experts/Advisors/Phase3CanonicalCandidate.ex5` |
| Candidate EX5 result | 303,546 bytes, produced 2026-09-15 11:52:02 +07:00 |
| Baseline EX5 | `outputs/build/mt5-latest/MQL5/Experts/Advisors/Phase3CanonicalBaseline.ex5` |
| Baseline EX5 result | 277,194 bytes, produced 2026-09-15 11:55:18 +07:00 |

The tester runtime is the repository-provisioned portable installation, while the
MetaEditor executable is the installed build `6182`. The compatible V82 Include tree
was selected by verifying that it declares both `CTrade::PositionClosePartial`
overloads used by the unchanged baseline source.

## Compile evidence

Compile command:

```text
metaeditor64.exe /compile:outputs/Mentor_RSI_MTF_v1.mq5 /log:outputs/build/phase3-canonical-compile-v82.log /inc:outputs/build/mt5-v82-runtime/MQL5
```

The selected include tree compiled both main-base and candidate sources with:

`Result: 0 errors, 0 warnings`

The earlier failed attempt with `outputs/build/mt5-latest/MQL5/Include` was an
incomplete-library mismatch; it was not used for the tester artifacts.

## Tester evidence

The sanity config used `BTCUSD`, `H1`, model `4`, `2023.04.01` through `2023.04.07`,
deposit `5000 USD`, leverage `1:10`, `ExecutionMode=0`, no optimization, no forward
mode, `UseLocal=1`, and `ShutdownTerminal=1`. Two attempts produced no report. The
portable log recorded:

```text
Network '103455393': no connection to Exness-MT5Real15
MQL5.community: authorization failed
Tester: not synchronized with trade server
Tester: terminal is not synchronized with the trade server before start automatic testing [1]
Tester: automatic testing started
```

Therefore the following values remain unset by design:

- tester sanity result
- baseline tester result
- candidate tester result
- signal difference count
- order difference count
- execution behavior difference count

No tester report was fabricated, and no FORWARD run, authorization, scheduler task,
or live activation was created.

## Exact next environment requirement

Restore terminal synchronization/authorization for `Exness-MT5Real15` in the
portable tester session (or provide an equivalent verified local history session),
then rerun the sanity test followed by V26 and V63 baseline-versus-candidate tests
with the exact configs. No trading code change is required by this diagnosis.
