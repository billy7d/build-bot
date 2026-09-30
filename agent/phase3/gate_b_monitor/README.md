# PR #6 Gate B Monitor V2 Automation

This package is offline-first and fail-closed. It implements the Stage 1/2/3
contracts for one future Gate B permission-monitor session without launching
MT5, MetaEditor, a production EA or any trading process.

## Components

- `PR6_ReadOnlyPermissionMonitor_V2.mq5` — new EA source; read-only
  `AccountInfo*`, `TerminalInfo*`, `MQLInfo*`, timer and `ExpertRemove()` only.
- `orchestrator.py` — approval/hash checks, atomic single-run lock, exact chart
  adapter boundary and no-retry state machine.
- `supervisor.py` — one-shot monotonic soft/hard deadline and independent-stop
  contract.
- `provisioning.py` — read-only dedicated-root preflight and an approval-gated
  empty-layout provisioner; it never installs or copies MT5 under this PRD.
- `startup.py` — credential-free `/portable` + `/config` startup generator for
  exactly one monitor on `BTCUSD,H1`, with live trading and DLL import denied.
- `compiler.py` — approval-gated MetaEditor command plan and compiler-log/
  source/EX5 verification; it does not run MetaEditor in offline mode.
- `controller.py` — dedicated acceptance preflight that composes isolation,
  startup and compile prerequisites and keeps launch/attach blocked until the
  required runtime approvals exist.
- `process_supervisor.py` — exact PID/path/creation/session/data-root identity
  binding, bounded graceful stop, authorization-gated emergency stop and an
  independent monotonic supervisor runner.
- `collector.py` — bounded raw journal copy, offset/hash provenance and V2
  sample parsing; it never uses stale JSONL as a live signal.
- `evaluator.py` — separate code, automation, functional, procedural,
  dedicated-acceptance, preflight and Gate B results.

The native MT5 adapter is intentionally absent. With the current CUA state
`apps=[]` (browser surfaces only), the supported result is `NO_SAFE_RUNTIME`
and no chart action is permitted. The proposed dedicated root
`D:\Trading\MT5-GateB-Acceptance` and external evidence root
`D:\Trading\MT5-GateB-Acceptance-Evidence` were not created. The shared
`D:\Trading\MT5-V26` root remains protected. Portable-mode behavior and
`FILE_COMMON` separation have only been encoded and preflighted offline; they
are not runtime proofs. The supervisor requires a stop callback bound to the
exact session/chart/process identity; a journal reader or `ExpertRemove()`
request is not an independent-stop or cleanup proof.

## Offline verification

```text
python -m compileall -q agent
python -m unittest agent.tests.test_gate_b_dedicated_components -v
python -m unittest agent.tests.test_gate_b_monitor_automation -v
python -m unittest agent.tests.test_mt5_watchdog -v
python -m unittest discover -s agent/tests
git diff --check
```

The tests use temporary files, fake adapters, simulated clocks and harmless
dummy processes. They do not compile or run MQL5, create the dedicated
terminal, use credentials or touch the approved V1/production paths. The
current result is `128/128` repository tests, including `16/16` dedicated
component tests, `16/16` existing Gate B automation tests and `10/10`
related watchdog tests. Dummy-process stop passed; the live MT5 hard deadline,
attach path and chart cleanup remain unproven.
