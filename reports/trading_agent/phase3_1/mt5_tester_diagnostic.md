# MT5 Tester Diagnostic — Phase 3.1 Canonical Telemetry

## Result

- `MT5_TESTER_STATUS`: `UNAVAILABLE_TERMINAL_NOT_SYNCHRONIZED`
- `MT5_EXECUTION_PARITY`: `NOT_VERIFIED`
- `MERGE_READY`: `NO`
- `LIVE_EXECUTION_ENABLED`: `NO`
- `FORWARD_COLLECTION_STATUS`: `READY`
- `ROOT_CAUSE_CLASSIFICATION`: `ENVIRONMENT_ERROR / ACCOUNT_TERMINAL_STATE_ERROR`

The tester sanity run was attempted four times. The third attempt used the
corrected MT5 config shape (`[Common]` Login/Server, `[Experts]`
`AllowLiveTrading=0`, single-separator EA/report paths), but it still failed to
synchronize. The original-vs-telemetry parity run was not started because no
valid sanity report was produced. The updated EA compiled into a new
tester-visible EX5, so the remaining failure is the terminal session/data
synchronization gate rather than an MQL compile failure.

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
| Candidate EX5 result | 305,704 bytes, produced 2026-09-16 11:16:57 +07:00 |
| Baseline EX5 | `outputs/build/mt5-latest/MQL5/Experts/Advisors/Phase3CanonicalBaseline.ex5` |
| Baseline EX5 result | 277,194 bytes, produced 2026-09-15 11:55:18 +07:00 |

All terminal binaries discovered on the host were build `6182`:

| Role | Path | Data readiness |
|---|---|---|
| Tester runtime used | `E:\build-bot\outputs\build\mt5-latest\terminal64.exe` | Cached `BTCUSD` tester history present |
| MetaEditor used | `D:\MetaTrader5\metaeditor64.exe` | Compile-only installation |
| Other terminal | `D:\MetaTrader5\terminal64.exe` | Default installation; no matching local MQL5/tester data observed |
| Other terminal | `C:\Program Files\MetaTrader 5\terminal64.exe` | Default installation; no matching local MQL5/tester data observed |

The tester runtime is the repository-provisioned portable installation, while the
MetaEditor executable is the installed build `6182`. The compatible V82 Include tree
was selected by verifying that it declares both `CTrade::PositionClosePartial`
overloads used by the unchanged baseline source.

## Compile evidence

Compile command:

```text
metaeditor64.exe /compile:outputs/Mentor_RSI_MTF_v1.mq5 /log:outputs/build/phase3-canonical-compile-v82-rerun.log /inc:outputs/build/mt5-v82-runtime/MQL5
```

The selected include tree compiled both main-base and candidate sources with:

`Result: 0 errors, 0 warnings`

The earlier failed attempt with `outputs/build/mt5-latest/MQL5/Include` was an
incomplete-library mismatch; it was not used for the tester artifacts.

## Tester evidence

The sanity config used `BTCUSD`, `H1`, model `4`, `2023.04.01` through `2023.04.07`,
deposit `5000 USD`, leverage `1:10`, `ExecutionMode=0`, no optimization, no forward
mode, `UseLocal=1`, and `ShutdownTerminal=1`. Four attempts produced no report;
the latest two launches used `outputs/build/phase3-canonical-sanity.ini` after the
config audit. The portable log recorded:

```text
Network '103455393': no connection to Exness-MT5Real15
MQL5.community: authorization failed
Tester: not synchronized with trade server
Tester: terminal is not synchronized with the trade server before start automatic testing [1]
Tester: automatic testing started
```

The latest attempt after the manual-login report also used the expected
Login/Server and live-trading-disabled sections, but logged the same failure
sequence in `logs/20260916.log`:

```text
11:10:28 Network '103455393': no connection to Exness-MT5Real15
11:10:28 MQL5.community authorization failed
11:11:16 Tester not synchronized with trade server
11:11:16 Tester terminal is not synchronized with the trade server before start automatic testing [1]
11:11:16 Tester automatic testing started
```

The fresh fourth invocation recorded `11:45:44 MQL5.community authorization
failed`, created no report, and produced no `authorized` or `terminal
synchronized` event in the portable log. The active GUI title showing the
expected account/server is not sufficient evidence that the tester process has
a synchronized trade-server session.

The expected writable report path was
`E:\build-bot\outputs\build\mt5-latest\reports\codex\phase3_canonical_sanity.html`;
it did not exist after the latest attempt. The historical `Tester\bases` tree
does contain `BTCUSD` tick files beginning `2023.04.01`, so the evidence points
to broker/account synchronization rather than missing symbol history or report
path permissions.

Therefore the following values remain unset by design:

- tester sanity result
- baseline tester result
- candidate tester result
- signal difference count
- order difference count
- execution behavior difference count

No tester report was fabricated, and no FORWARD run, authorization, scheduler task,
or live activation was created. No automated login or credential change was
attempted.

## Exact next environment requirement

Restore a valid authorized/synchronized `Exness-MT5Real15` session for the
portable tester (or provide an equivalent verified local-history terminal
session), then rerun sanity followed by V26 and V63 baseline-versus-candidate
tests with the exact configs. The manual/environment requirement is a successful
terminal log sequence containing `authorized` and `terminal synchronized` before
the tester run. No trading code change is required by this diagnosis.
