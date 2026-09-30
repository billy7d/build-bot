# PR #6 Gate C Lite policy-change proposal

Status: APPROVED

This document proposes a controlled acceptance-policy change. It does not
replace or silently weaken the current PRD/acceptance contract. The operator
approved the bounded policy scope with the required identity, UTC timestamp
and scope. The original Gate C remains normative for all deferred claims and
Gate C Lite is not an execution result until a separate execution approval is
present.

## Source contract reconciled

The proposal was reconciled against:

- PR #6 Conditional Execution Plan, especially section D Operational
  acceptance and its fail-closed sequence:
  `windows-24x7-acceptance-20260917/AcceptanceRoot/final-operator-acceptance-20260919T032715Z/execution-plan.md`.
- The original operational acceptance contract and merge-readiness record:
  `windows-24x7-acceptance-20260917/AcceptanceRoot/final-operator-acceptance-20260919T032715Z/operational-acceptance.json`
  and `windows-24x7-acceptance-20260917/AcceptanceRoot/final-operator-acceptance-20260919T032715Z/merge-readiness.json`.
- docs/trading_agent/forward_ops/BOOTSTRAP.md.
- docs/trading_agent/forward_ops/FORWARD_HANDOFF.md.
- docs/trading_agent/forward_ops/FORWARD_RUNBOOK.md.
- docs/trading_agent/forward_ops/RECOVERY.md.
- The approved PR #6 dual-node architecture and current operator checkpoint.

The frozen source SHA, package manifest, model, history index, EA/preset
bindings, telemetry schemas, risk controls and execution-inert contracts are
unchanged by this proposal.

## Old criterion

The existing Gate C/full operational acceptance proves a fresh clean Windows
node/VM can be trusted and operated end to end. It includes:

- clean Windows provisioning/baseline and trusted bootstrap;
- handoff and health/state continuity;
- non-destructive backup and isolated restore;
- takeover checks and acknowledgements;
- separately approved Windows lock/logoff/reboot and recovery behavior;
- evidence that the environment is suitable for the intended operational
  posture, not merely for a local smoke test.

The old gate is intentionally broader than a single-host smoke test. It is
the only criterion that can support the corresponding clean-node/24-7 claims.

## Proposed criterion: Gate C Lite

Gate C Lite is a bounded operational smoke test on the existing MSI host,
using a new empty acceptance runtime and operations root outside the immutable
source checkout. It has exactly four checks:

### C1. Trusted bootstrap

After a policy approval and a separate execution approval are present, and
after Gate B package trust is PASS, bootstrap only into a separate acceptance
directory. Verify the approved source SHA, package manifest identity and
artifact checksums. Refuse any non-empty target or any existing authorization/
run. Never overwrite an existing runtime and never touch the production
runtime.

### C2. Health and state

Run read-only status and health commands. Confirm source identity, checkpoint
and reported runtime state are internally consistent. A stopped collector with
no authorization is valid for this smoke test; ACTIVE is not required and
must not be fabricated.

### C3. Backup and isolated restore

Use only data that is declared in the execution approval and has actual
evidence. A real data source may be copied safely into the acceptance runtime
only when the governing contract permits that copy and the approval records
the source evidence, copy authorization, runtime path and checksum. A fixture
must be isolated, explicitly identified as test-only, and never treated as
production data. The runner does not create data, authorization, a FORWARD run,
or a collector to obtain input data.

If an eligible runtime source and checkpoint are present, create a
non-destructive backup. Verify the backup checksum, raw prefix/checkpoint
consistency and SQLite integrity, then restore into a new empty isolated
directory and compare the before/after identity, checkpoint and integrity
evidence. If the eligible source is absent or unverified, report C3 as
`BLOCKED`. If the eligible source is an isolated fixture, report
`TEST_ONLY_PASS`; never report production acceptance PASS.

### C4. Safety invariants

Confirm that the smoke test created no FORWARD authorization, no FORWARD run,
no Scheduler, no execution authority, no order placement, and no production
runtime change. Keep LIVE_EXECUTION_ENABLED=NO and all execution/trade
authorities at NONE.

## What Gate C Lite proves

If policy-approved, Gate C Lite can prove that the approved package can be
bootstrapped into a separate MSI acceptance root and that the implemented
runtime status/health/backup/isolated-restore safety surfaces work for the
bounded evidence available. It can also prove that this smoke run itself did
not create activation authority or modify production runtime.

Gate C Lite does not prove clean Windows provenance, VM isolation, host
reboot/recovery behavior, cross-machine takeover, or long-duration stability.
It does not turn the MSI host into a clean acceptance node and does not
authorize trading or production activation.

## Deferred acceptance

The following remain deferred to a separately approved 24/7 readiness run:

- clean Windows bootstrap and clean baseline;
- Windows lock/logoff/reboot operational tests;
- Windows recovery;
- cross-machine takeover;
- long-duration stability and persistence;
- any claim that the node is 24/7 READY or production activation READY.

The deferred items remain OPEN/NOT_RUN. They must not be marked PASS by a
successful Gate C Lite run.

## Independent approval records

`POLICY_APPROVAL` and `EXECUTION_APPROVAL` are separate records with separate
purposes. Neither record may be generated, signed or inferred by the runner.

### POLICY_APPROVAL_SCHEMA

Schema: `pr6-gate-c-lite-policy-approval/1`.

This record only confirms that the operator accepts the Gate C Lite scope, the
deferred tests and the stated limits. It must contain the proposal ID,
`policy_status=APPROVED`, operator identity, UTC timestamp, approved scope,
the exact deferred-test list, and explicit acknowledgement of the limits. It
must not be used to claim Gate A/B or runtime prerequisites.

### EXECUTION_APPROVAL_SCHEMA

Schema: `pr6-gate-c-lite-execution-approval/1`.

This separate record is valid only when the listed evidence files are real and
current and all execution prerequisites are `PASS`: Gate A, Gate B, package
trust, MSI non-trading enforcement, exact MT5 preflight, real telemetry,
separate acceptance roots, Scheduler disabled, and execution authority NONE.
It must also declare the C3 data source mode and evidence. The runner refuses
to run if either record, any evidence file, or any prerequisite is missing or
invalid.

The prepared runner `scripts/phase3/gate_c_lite_smoke.ps1` does not sign or
create either record. It does not sign an attestation, create a FORWARD
authorization, start a collector, install Scheduler, place an order, reboot
the host, or modify production runtime.

No precondition may be satisfied by a mock, replay, synthetic telemetry,
fixture or stale state when a real execution prerequisite is required. A
fixture is permitted only as the explicitly marked C3 `TEST_ONLY_PASS` data
source after the independent execution approval exists.

## Decision requested

OPERATOR_ACTION=POLICY_APPROVAL_RECORDED
POLICY_APPROVAL_PATH=D:\Trading\acceptance\pr6-c-lite-20260919\policy-approval.json
POLICY_APPROVAL_OPERATOR_ID=billy7d
POLICY_APPROVAL_UTC=2026-09-19T19:38:29.7594403Z
POLICY_APPROVAL_SOURCE=OPERATOR_DIRECTIVE

The policy decision is recorded. Execution remains separately gated:

    GATE_C_POLICY_APPROVED=YES
    GATE_C_LITE=NOT_RUN
    MERGE_READY=NO
    ACTIVATION_READY=NO
