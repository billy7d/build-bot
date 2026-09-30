# Agent handoff — 2026-10-01

## Purpose

This document is the continuation point for the next agent. It describes the
work prepared in the current workspace, the evidence-backed limits, the files
that are safe to publish, and the exact actions that remain operator-gated.

The repository is `https://github.com/billy7d/build-bot.git`. The working tree
started on `main` at `180e0e9` (`origin/main`). The handoff commit and push are
the source of truth for the final published SHA; do not infer a SHA from an
older report.

## Work completed in this workspace

### Gate B monitor V2 — offline implementation

`agent/phase3/gate_b_monitor/` contains a fail-closed, offline-first package:

- reviewed read-only MQL5 monitor source;
- typed permission/evidence models and bounded collector;
- exactly-once orchestration with an absent-native-surface hard stop;
- dedicated-root validation and credential-free startup configuration;
- approval-gated MetaEditor compile planning;
- exact PID/path/creation/session/data-root process identity checks;
- independent soft/hard-deadline supervisor and emergency-stop authorization;
- evaluator fields that keep functional, procedural, cleanup, chart-close and
  Gate B results separate.

The package does not launch MT5, open a chart, attach an EA, log in, compile
MQL5, create a terminal, or place an order by itself.

### Gate C Lite

The policy proposal, runbook and status are present under
`docs/trading_agent/phase3/`. Policy approval is recorded in the evidence
history, but no separate `EXECUTION_APPROVAL` exists and Gate C has not run.
Gate C Lite is not a Gate B bypass and is not an activation or trading
approval.

### Approval A1/R3 preparation

`tools/gate_b_a1_cleanup_admin.ps1` and the accompanying report under
`reports/trading_agent/phase3/` implement and document an exact-target,
administrator-gated cleanup dry-run. The non-admin sandbox dry-run reached
the core checks but correctly stopped with deferred process/service/task/
startup reads. It is not a full pass.

### PR #6 dual-node handoff (local-only)

The workspace contained `outputs/pr6-dual-node-handoff-20260919/`, a transfer
bundle containing read-only verifiers, package checksums, evidence templates
and an approval-gated second-machine procedure. It is intentionally **not
published** by this commit: its checksum-sensitive files were touched by
Windows line-ending/whitespace handling during integration, so the local copy
must not be treated as an approved byte-preserved package. Recover or rebuild
the bundle in a byte-preserving workspace and revalidate every manifest before
transferring it.

The intended safety invariants remain:

```text
LIVE_TRADING=NO
ORDER_PLACEMENT=NO
EXECUTION_AUTHORITY=NONE
TRADE_CONTROL_AUTHORITY=NONE
PRODUCTION_SCHEDULER=DISABLED
AUTO_MERGE=NO
AUTO_ACTIVATION=NO
```

Before any future second-machine transfer, read the recovered bundle
`AGENTS.md`, `README.md` and `RUN_ON_SECOND_MACHINE.md`, then run
`scripts/verify_pr6_handoff.ps1` before any other action. A verifier failure is
a hard stop.

## Verification performed

The commands below were run from the repository root with Python 3.12.1:

```text
python -m compileall -q agent                         PASS
python -m unittest discover -s agent/tests             45/45 PASS
python -m unittest agent.tests.test_gate_b_dedicated_components  16/16 PASS
python -m unittest agent.tests.test_gate_b_monitor_automation    16/16 PASS
```

The tests use temporary files, fake adapters, simulated clocks and harmless
dummy processes. They prove offline contracts only. They do not prove native
MT5 behavior, MetaEditor compilation, chart attachment, live process cleanup,
continuous telemetry, or trading safety.

The following remain unverified or not run:

- MQL5/MetaEditor compile of the new V2 source;
- native MT5 GUI/control-surface attach and chart cleanup;
- real dedicated terminal/data-root/`FILE_COMMON` isolation;
- real MT5 hard-deadline process stop;
- Gate B runtime acceptance and real telemetry;
- Gate C Lite execution, clean Windows recovery, takeover and long-duration
  stability.

## Current blockers and required safety boundary

The current classification remains `GATE_B_OVERALL=BLOCKED` and
`MERGE_READY=NO` for the operational acceptance work.

The A1 attempt created an unapproved default installation at
`C:\Program Files\MetaTrader 5` instead of the requested dedicated root
`D:\Trading\MT5-GateB-Acceptance`. A1-R3 is waiting for an operator running
an elevated 64-bit PowerShell session to complete the exact cleanup dry-run.
The operator must first verify the script hash, then require exit code `0` and
`DRY_RUN_STATUS=PASS` before execute mode. Any mismatch is a stop; do not
delete, move, update or broadly terminate a terminal from the agent.

After cleanup evidence is returned, the agent must independently re-check the
failed root and protected `D:\Trading\MT5-V26` before considering one separately
approved A1 reinstall. A2 and Approval B remain separate decisions.

The earlier monitor session also has a documented procedural deviation and a
10-minute/30-minute contract conflict. Read
`GATE_B_MONITOR_V2_CONTRACT_AMENDMENT.md` and the deviation report before any
rerun. Do not promote historical functional samples to procedural compliance
or Gate B PASS.

No credential, private key, authorization record, Scheduler task, FORWARD run,
AutoTrading enablement, order, deal or live-trading approval was created by
this handoff.

## Recommended next-agent sequence

1. Start from the pushed `main` commit and run `git status --short --branch`.
2. Read this file, `README.md`, the Gate B runbook/contract amendment and the
   PR #6 bundle instructions before touching scripts or runtime state.
3. Keep the source checkout immutable while a forward run is active. Never
   reset/clean a dirty checkout to satisfy a package SHA check; use a separate
   clean checkout at the explicitly approved SHA.
4. Wait for operator A1-R3 evidence. Validate the exact target, process,
   service, task, startup-reference and V26 post-cleanup evidence.
5. Only after A1 is independently PASS, obtain a separate short-control/A2
   authorization. Then obtain Approval B for any real monitor session.
6. If the native MT5 surface is still unavailable, report `NO_SAFE_RUNTIME` and
   stop before lock creation, chart attach or terminal launch.
7. For second-machine work, first recover a byte-preserved PR #6 bundle and
   run its handoff verifier. Preserve all fixed package/source hashes. Do not
   sign, create a VM, install a scheduler, create authorization or activate a
   forward run without the stated operator approvals.

## Published versus local-only files

The commit contains source, tests, runbooks, aggregate reports and A1-R3
tooling. The PR #6 transfer bundle is local-only until it is recovered or
rebuilt byte-preserved and independently revalidated. Local runtime captures are intentionally ignored
by `.gitignore` because they contain account/server/IP/trade-history or terminal
backup material. In particular, do not force-add:

- `outputs/forward_evidence/`;
- `outputs/smoke_runs/` and `outputs/smoke_automation/`;
- `outputs/gate_b_msi_investor_acceptance_*/`;
- `outputs/gate_b_msi_monitor_deviation_review_*/`;
- `outputs/gate_b_msi_monitor_v2_automation_*/`;
- `outputs/pr6-dual-node-handoff-20260919/` (checksum-sensitive local bundle);
- `windows-24x7-acceptance-*/` (including the embedded `InstallRoot` repo);
- `reports/trading_agent/phase3_forward_node_ops/gate_b_msi_investor_acceptance.md`.

The local copies remain available for the operator and can be summarized or
redacted in a future, explicitly approved evidence commit.

## Handoff completion check

After the handoff commit, confirm:

```powershell
git status --short --branch
git log -1 --oneline --decorate
git remote -v
```

The remote must be `origin` at the project GitHub URL and the pushed branch must
be `main`. The next agent should treat the pushed commit as the reproducible
starting point and this document as the operational boundary, not as evidence
that any blocked runtime gate has passed.
