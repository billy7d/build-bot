# MT5 tester diagnostic and recovery

## Status

```text
MT5_TESTER_STATUS: PASS
MT5_EXECUTION_PARITY: PASS
EXECUTION_BEHAVIOR_DIFFERENCE_COUNT: 0
```

## Installation and runtime audit

Two installed MetaTrader 5 binaries were identified, both build `5.0.0.6182`:

- `C:\Program Files\MetaTrader 5\terminal64.exe`
- `D:\MetaTrader5\terminal64.exe`

The intended tester was selected explicitly as the portable build under
`E:\build-bot\outputs\build\mt5-latest`, because its terminal, MetaEditor,
MetaTester, `Bases`, `MQL5`, `Tester`, and report directories are co-located.
The terminal log confirms that exact portable root. Its tester-visible paths are:

- Terminal: `E:\build-bot\outputs\build\mt5-latest\terminal64.exe`
- MetaEditor: `E:\build-bot\outputs\build\mt5-latest\MetaEditor64.exe`
- MetaTester: `E:\build-bot\outputs\build\mt5-latest\metatester64.exe`
- Data/runtime root: `E:\build-bot\outputs\build\mt5-latest`
- Experts: `E:\build-bot\outputs\build\mt5-latest\MQL5\Experts\Advisors`
- Tester logs: `E:\build-bot\outputs\build\mt5-latest\Tester\logs`
- Agent logs: `E:\build-bot\outputs\build\mt5-latest\Tester\Agent-127.0.0.1-3000\logs`
- Reports: `E:\build-bot\outputs\build\mt5-latest\reports\codex`

The runtime contains `BTCUSD` history/ticks for April–December 2023. The
January–March tick files required by the old January-starting window were not
present. The exact symbol `BTCUSD` was present and synchronized on
`Exness-MT5Real15`; no alias such as `XAUUSD.a` was substituted.

## Evidence for `-1000012355`

The failed startup at `17:08` initialized the old baseline config, then logged:

```text
Network '103455393': no connection to Exness-MT5Real15
MQL5.community authorization failed
Tester not synchronized with trade server
terminal is not synchronized with the trade server before start automatic testing [1]
automatic testing started
```

No tester completion, non-empty report, or successful run marker followed that
attempt. This is classified as an environment/configuration/data/deployment
failure, not as a strategy-logic failure:

```text
ENVIRONMENT_ERROR
TESTER_CONFIG_ERROR
SYMBOL_DATA_ERROR
EX5_PATH_ERROR
```

The report directory itself was writable once the tester was synchronized; the
recovered runs created non-empty reports and exited with terminal code `0`.

## Recovery actions

The following deployment-only corrections were made in the portable runtime:

1. Compiled the exact base source into the baseline artifact and deployed it as
   `MQL5\Experts\Advisors\Phase31Baseline.ex5`.
2. Deployed the current branch artifact as
   `MQL5\Experts\Advisors\Phase31Telemetry.ex5`.
3. Copied the existing `79_v26_forward_demo.set` to the tester-visible
   `MQL5\Profiles\Tester` directory.
4. Used `BTCUSD`, `H1`, model `4`, and the deterministic cached range
   `2023.04.01`–`2023.12.31` for both participants.
5. Wrote reports to the local writable `reports\codex` directory with
   `ReplaceReport=1` and `ShutdownTerminal=1`.

No trading source, model, bundle, cutoff, similarity/history, V26/V63, risk,
lot, SL/TP, gate, forward authorization, or activation code was changed.

## Run evidence

The minimal sanity run produced a `73558`-byte report, `522706` real ticks,
`144` bars, and `6` trades. The official baseline report is `304298` bytes and
the candidate report is `304622` bytes. Both report and tester logs contain
`Test passed`, `OnTester result 0`, and terminal shutdown code `0`.

Raw reports and logs stay outside Git. The sanitized paths, hashes, configs,
and comparison counts are in `execution_parity.json`.
