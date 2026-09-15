# Persistent runtime validation

## Implementation

- `E:\build-bot\agent\phase3\forward.py` owns the local runtime config, frozen asset gates, authorization manifest, run marker, byte offsets, heartbeat, OS lock, and persistent collector loop.
- `E:\build-bot\agent\phase3\cli.py` exposes `build-history-index`, `prepare-forward`, `start-forward`, `resume-forward`, `stop-forward`, and `status-runtime`.
- `E:\build-bot\scripts\phase3\` contains idempotent install/start/stop/status/uninstall helpers and a log-rotating runner.
- The default Task Scheduler installation is disabled/stopped. It uses the interactive user token, `IgnoreNew`, unlimited execution time, and no stored password.

## Evidence

The full local suite passed `52/52` tests. Phase 3.1 covers:

- complete-line parsing, partial final line, genuine rotation, and same-identity truncation;
- persisted offset, restart, deterministic duplicate rejection, and rebind of a new run only after the previous run is stopped;
- active OS lock rejection and stale lock-text recovery;
- authorization hash/assets/gates, missing authorization rejection, frozen model/index gates, and runtime machine status;
- `start-shadow --mode FORWARD` refusal and zero execution API path count.

The temporary migration fixture returned `PRAGMA integrity_check=ok` and no
foreign-key violations. No runtime root, Task Scheduler task, runtime DB, or
collector process was created.

## Intended runtime boundary

```text
E:\build-bot-runtime\phase3\
  config\
  telemetry\
  db\
  logs\
  state\
  control\
```

The collector binds the first observed source at current EOF. It then resumes
the persisted offset on restart, allows a genuine file rotation, and fails the
run closed on same-identity truncation. A stale lock file does not block
recovery because the collector uses an operating-system file lock held for the
process lifetime.

Real collector event-to-prediction latency and backlog measurements are
`NOT_MEASURED` because no real MT5 source was available. Fixture correctness
and bounded polling behavior are covered by the contract tests.
