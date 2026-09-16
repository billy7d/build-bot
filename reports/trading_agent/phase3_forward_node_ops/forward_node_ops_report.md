# Phase 3 Forward Node Operations — Implementation Report

## Scope

This PR adds the operational surface for a fresh Windows forward node: an
artifact-checked deployment package builder, fail-closed bootstrap, MT5
preflight, atomic persistent handoff, read-only health observer, WAL-safe
backup/isolated restore, cross-machine migration plan and agent takeover
acknowledgement. The existing collector, canonicalization, model, bundle,
cutoff and execution-inert boundary are not changed.

Dynamic state belongs outside the checkout. The source checkout is immutable
while a run is active; runtime and operations roots are explicit parameters and
have no fixed drive-letter default.

## Status at implementation commit creation

The machine-readable source of truth is
`forward_node_ops_status.json`. Current status is deliberately conservative:

```text
CODE_IMPLEMENTATION_STATUS=PASS
CLEAN_WINDOWS_BOOTSTRAP_STATUS=NOT_RUN
ARTIFACT_INTEGRITY_STATUS=TEST_ONLY_PASS_PRODUCTION_PACKAGE_NOT_CREATED
HANDOFF_STATUS=TEST_ONLY_PASS
BACKUP_STATUS=TEST_ONLY_PASS
RESTORE_DRILL_STATUS=TEST_ONLY_PASS
AGENT_TAKEOVER_STATUS=TEST_ONLY_PASS
WINDOWS_TEST_STATUS=NOT_RUN
PYTHON_TESTS=86/86 PASS
COMPILEALL=PASS
POWERSHELL_PARSE=PASS
EXECUTION_API_PATH_COUNT=0
LIVE_EXECUTION_ENABLED=NO
FORWARD_AUTHORIZATION_STATUS=NOT_CREATED
FORWARD_RUN_ID=NOT_CREATED
SCHEDULER=NOT_INSTALLED_OR_DISABLED
MERGE_READY=NO
```

CI fields are marked `PENDING_EXACT_HEAD_CI` at commit creation. They must be
rechecked on the exact pushed head and recorded separately; an old PR result is
not reused.

## Test boundary

The new 23-case suite exercises package tamper/missing-artifact stops, bootstrap
idempotency and existing-state protection, atomic handoff, stale heartbeat,
partial JSONL, online backup, raw/checkpoint consistency, isolated restore,
corruption rejection, migration continuity refusal, MT5 journal/schema gate,
Scheduler duplicate policy and takeover mismatch. These are `TEST_ONLY`
fixtures. They do not prove a clean Windows GUI/MT5 account, Task Scheduler
lock/logoff/reboot behavior or production artifact provenance.

## Safety stop

```text
DO_NOT_MERGE=YES
DO_NOT_ACTIVATE_FORWARD=YES
DO_NOT_CREATE_PRODUCTION_AUTHORIZATION=YES
DO_NOT_START_SCHEDULER=YES
EXECUTION_AUTHORITY=NONE
TRADE_CONTROL_AUTHORITY=NONE
LIVE_EXECUTION_ENABLED=NO
READY_FOR_PHASE4=NO
```
