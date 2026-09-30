# Gate C Lite MSI runbook

This runbook is preparatory only. Do not execute it while the policy proposal
is `DRAFT_PENDING_OPERATOR_APPROVAL`. The original Gate C remains normative
until the operator supplies both independent approval records.

## Required before execution: two independent approvals

`POLICY_APPROVAL` has schema `pr6-gate-c-lite-policy-approval/1`. It only
approves the Gate C Lite scope, the deferred tests and the limits. It does not
assert Gate A/B or any execution prerequisite.

`EXECUTION_APPROVAL` has schema `pr6-gate-c-lite-execution-approval/1`. It is
valid only when the approval contains current evidence paths and `PASS` for
Gate A, Gate B, package trust, MSI non-trading enforcement, exact MT5
preflight, real telemetry, separate acceptance roots, Scheduler disabled and
execution authority NONE.

The two records must be separate files. The runner refuses a missing record,
wrong schema/type, missing evidence file, or any non-PASS execution
prerequisite. The runner does not create or sign either record.

The acceptance runtime and ops roots must be new, empty, separate from
production, and outside the source checkout.

The source checkout must be clean at:

    bbf87b40eb72de35318608cb9e4d4f77d150e32a

The package must independently verify to the approved manifest and artifact
identities. Do not substitute a fixture for production evidence. If a fixture
is intentionally used, it must be declared as `ISOLATED_FIXTURE` in the
execution approval, pass `-TestOnly`, and result in `TEST_ONLY_PASS` only.

## C3 data-source rule

The execution approval must declare one of:

- `VERIFIED_REAL_COPIED`: real data with actual evidence, contract permission
  for the copy, an acceptance-runtime path, checkpoint evidence and a matching
  SHA-256; or
- `ISOLATED_FIXTURE`: an isolated fixture with a matching SHA-256, explicit
  test-only status, and no production use.

The runner does not create authorization, a FORWARD run, or a collector to
generate C3 data. Missing, stale, unverified or unavailable runtime data makes
C3 `BLOCKED`. A fixture may produce only `TEST_ONLY_PASS`.

## MSI command after approval

Run from the repository checkout on MSI. Replace only the paths and the
operator-supplied trusted manifest digest with approved values. The command is
provided for later use and was not run during handoff preparation:

    & 'D:\Trading\buildbot\scripts\phase3\gate_c_lite_smoke.ps1' `
      -PolicyApprovalPath 'D:\Trading\acceptance\pr6-c-lite-20260919\policy-approval.json' `
      -ExecutionApprovalPath 'D:\Trading\acceptance\pr6-c-lite-20260919\execution-approval.json' `
      -InstallRoot 'D:\Trading\buildbot' `
      -RuntimeRoot 'D:\Trading\acceptance\pr6-c-lite-20260919\runtime' `
      -OpsRoot 'D:\Trading\acceptance\pr6-c-lite-20260919\ops' `
      -PackagePath 'D:\Trading\acceptance\pr6-c-lite-20260919\package' `
      -TrustedManifestDigest '<64-hex-approved-trusted-manifest-digest>' `
      -ProductionRuntimeRoot 'D:\Trading\production-runtime' `
      -ReportPath 'D:\Trading\acceptance\pr6-c-lite-20260919\gate-c-lite-result.json' `
      -OperatorApprovalConfirmed

The runner refuses non-empty targets, source identity drift, package identity
drift, missing approvals/evidence/prerequisites, existing authorization/run
state, live execution, Scheduler matches, or critical health. It does not
sign, create approval records, create authorization, start a collector,
install Scheduler, place orders, reboot the host, or modify the production
runtime.

## Result interpretation

Record C1 through C4 and the deferred list exactly as emitted. A successful
Gate C Lite run is bounded MSI smoke evidence only. It must not set
`24/7_READY`, `ACTIVATION_READY`, or merge authority to YES. The deferred
clean-Windows, Windows lock/logoff/reboot operational, recovery,
cross-machine takeover, and
long-duration tests remain OPEN/NOT_RUN.
