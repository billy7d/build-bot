# MT5 telemetry watchdog (V26/V63)

`agent.phase3.mt5_watchdog` is a telemetry-only observer and fail-closed
recovery helper. It does not import a trading API, alter an EA, create a
FORWARD authorization/run, register a Windows task, or enable AutoTrading.
Mutable retry state and incident evidence belong under the operator-supplied
`ops_root`, not in the checkout.

## Required identity evidence

Each instance entry must name the exact `terminal_exe`, install/data directory,
profile, EA EX5 and preset, expected account/server, and telemetry path/schema.
`approved_ex5_sha256` and `approved_preset_sha256` are mandatory. The operator
must provide two read-only JSON attestations:

* `trading_permission_evidence_path` with `auto_trading=false`,
  `terminal_trade_allowed=false`, `mql_trade_allowed=false`,
  `live_execution_enabled=false`, and both authorities set to `NONE`.
* `ea_status_evidence_path` with the exact EA name, account/server, chart
  symbol/timeframe, `attached=true`, and a successful `on_init` result.

Missing, malformed, mismatched, or stale identity evidence is a hard stop. A
terminal process is matched by exact executable path; duplicate matches,
unverified data-directory/profile command-line identity, or an unavailable
Windows process query also stop recovery.

## Commands

From the repository root:

```powershell
python -m agent.phase3 mt5-watchdog-status --config .\docs\trading_agent\forward_ops\mt5-watchdog-config.example.json
python -m agent.phase3 mt5-watchdog-health --config .\docs\trading_agent\forward_ops\mt5-watchdog-config.example.json
python -m agent.phase3 mt5-watchdog-dry-run --config .\docs\trading_agent\forward_ops\mt5-watchdog-config.example.json --instance V26
python -m agent.phase3 mt5-watchdog-recover-once --config <operator-config> --instance V26
```

The PowerShell wrapper `scripts/phase3/mt5_watchdog.ps1` exposes the same
actions (`status`, `health`, `dry-run`, `recover-once`, `start`, `stop`).
`start` and `stop` only report `NOT_INSTALLED_OR_DISABLED`; persistent service
or Scheduled Task installation requires separate operator approval and is not
performed by this PR.

## Recovery and health semantics

Only an absent terminal is eligible for a one-time start. A running terminal
with a stale exporter is observed and incidented; a second terminal is never
opened and an EA is never removed/re-added automatically. Launch arguments are
explicit, passed as an argument array with `shell=false`, and credential/server
overrides or unapproved portable mode are rejected.

The watchdog validates JSONL schema, last valid record/timestamp, byte size,
source identity, sequence continuity and age. Invalid JSON/schema, sequence
gaps, source drift, checkpoint conflicts and read errors are hard stops; a
stale stream is classified as health trouble and is not repaired by fabricating
records. Restart attempts are persisted outside Git and a circuit breaker opens
after two attempts in 30 minutes. Pre-launch snapshots contain metadata only;
historical telemetry, raw JSONL, checkpoints and databases are never truncated,
rewound, overwritten or merged.

All command results include `trading_action=NONE`,
`forward_authorization=NOT_CREATED`, and `forward_run_id=NOT_CREATED`.
