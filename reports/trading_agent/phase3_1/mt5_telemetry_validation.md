# MT5 telemetry validation

## Audit result

`EXISTING_TELEMETRY_REUSABLE = NO`.

The existing `Mentor_RSI_MTF_forward.csv` writer records account/connectivity,
fill, risk, and execution fields. It is not the Phase 2 opportunity feature
schema, so Phase 3.1 adds an independent JSONL side-channel in
`E:\build-bot\outputs\Mentor_RSI_MTF_v1.mq5`.

## Exporter contract

- Schema: `phase3-live-telemetry/1`.
- Storage: `FILE_COMMON`, one complete line followed by flush.
- Event timestamp: the closed `lastEntryBarTime`, converted to UTC; bar state is `closed_bar`.
- Emission: `void EmitPhase3Telemetry(...)`, called after the existing order request returns; its result is not read by strategy logic.
- Source ID: deterministic from strategy version, symbol, timeframe, UTC opportunity time, side, and `EXECUTION_CANDIDATE`.
- Event-time features include the registered RSI/ATR/spread/StdDev/regime fields plus `entry_price`, `risk_distance`, and `initial_sl_distance`.
- No outcome, future-bar, label, or future-return field is emitted.
- Tester mode skips live JSONL opening, so historical tester runs cannot masquerade as live evidence.

The expected physical path is:

```text
C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\Common\Files\phase3\Mentor_RSI_MTF_<MagicNumber>_<Symbol>_<Timeframe>.jsonl
```

The common `Files\phase3` directory was checked and contained no live source
file. No MT5 process was running after the controlled tester attempts.

## Compile and live evidence

MetaEditor compiled the changed source with the V82 runtime include and
reported `0 errors, 0 warnings`. The actual live connection gate is
`UNAVAILABLE`: no live exporter path, process, schema record, or source write
was observed. No synthetic JSONL record was used to claim connection.

Exporter p50/p95/max duration is `NOT_MEASURED` because MT5 could not provide a
live event. The source-level failure isolation is preserved: open/write errors
are warnings in the independent exporter and do not return a strategy control
flag.
