# Phase 3 Forward Node Operations — Final Acceptance Evidence

## Scope and acceptance posture

PR #6 adds the operational surface for a fresh Windows forward node: an
artifact-checked deployment package builder, fail-closed bootstrap, MT5
preflight, atomic persistent handoff, read-only health observer, WAL-safe
backup/isolated restore, cross-machine migration plan and agent takeover
acknowledgement. Trading logic, canonicalization, model, bundle, cutoff and
the execution-inert boundary are unchanged.

This acceptance pass reconciles the implementation evidence and deliberately
stops short of production acceptance. The current checkout is not a clean
Windows host, a valid frozen historical similarity index is not available, and
the production EA/preset pair has not been selected and independently approved.
No production package, authorization, run or Scheduler task was created.

The machine-readable source of truth is
`forward_node_ops_status.json` in this directory.

## Required status fields

```text
PR_URL=https://github.com/billy7d/build-bot/pull/6
BASE_SHA=b6042bc4055931092b190a1e57af0798e1a96189
INITIAL_CANDIDATE_HEAD=f671f709c5bd9820c8f9de7a3dece9a526e4f379
EVIDENCE_GENERATION_HEAD=f671f709c5bd9820c8f9de7a3dece9a526e4f379
FINAL_HEAD_SHA=SEE_FINAL_PR_HEAD_AFTER_THIS_EVIDENCE_COMMIT
CLEAN_WINDOWS_HOST=NOT_AVAILABLE
CLEAN_WINDOWS_BOOTSTRAP_STATUS=BLOCKED_NO_WINDOWS_HOST
ARTIFACT_INVENTORY_STATUS=BLOCKED_EXTERNAL_INPUT
PRODUCTION_PACKAGE_STATUS=NOT_CREATED
DETACHED_ATTESTATION_STATUS=PENDING_OPERATOR
PACKAGE_SHA256=NOT_CREATED
MT5_PREFLIGHT_STATUS=BLOCKED_NO_OPERATOR_APPROVED_MT5_ACCEPTANCE_ENVIRONMENT
WINDOWS_LOCK_TEST=NOT_RUN
WINDOWS_LOGOFF_TEST=NOT_RUN
WINDOWS_REBOOT_TEST=NOT_RUN
BACKUP_STATUS=TEST_ONLY_PASS
RESTORE_DRILL_STATUS=TEST_ONLY_PASS
AGENT_TAKEOVER_STATUS=TEST_ONLY_PASS
PHASE2_CI=SUCCESS_ON_IMPLEMENTATION_HEAD; PENDING_ON_FINAL_HEAD
PHASE3_CI=SUCCESS_ON_IMPLEMENTATION_HEAD; PENDING_ON_FINAL_HEAD
PHASE3_1_CI=SUCCESS_ON_IMPLEMENTATION_HEAD; PENDING_ON_FINAL_HEAD
EXECUTION_API_PATH_COUNT=0
LIVE_EXECUTION_ENABLED=NO
EXECUTION_AUTHORITY=NONE
TRADE_CONTROL_AUTHORITY=NONE
FORWARD_AUTHORIZATION_STATUS=NOT_CREATED
FORWARD_RUN_ID=NOT_CREATED
SCHEDULER=NOT_INSTALLED_OR_DISABLED
MERGE_READY=NO
```

`FINAL_HEAD_SHA` is intentionally not self-referential: the exact final
commit SHA is reported after the evidence commit and exact-head CI check. The
pre-commit implementation SHA above is the SHA whose code and original CI
results were audited.

## Frozen artifact inventory

| Artifact | Result | Evidence |
| --- | --- | --- |
| Phase 3 bundle manifest | `AVAILABLE_VERIFIED` | `reports/trading_agent/phase3/shadow_bundle_manifest.json`; SHA-256 `371076fa51d5150667164c293a3a57c6ef5f02466f4030a34fc641a83f4b491f` |
| Phase 2 model bundle | `AVAILABLE_VERIFIED_CONTRACT_LOCAL_ONLY` | Git-ignored local file; model payload fingerprint `398368efdc4867845a0b4880308fe0ff61297463177aa6ee11a7c8f7e4ace5f8`; not independently approved for packaging |
| Historical similarity index | `MISSING` | Required schema `phase3-historical-similarity-index/1` with non-empty frozen rows was not found |
| Phase 2 similarity results | `NOT A SUBSTITUTE` | `similarity_results.json` is validation output, not the frozen index artifact; it was not rebuilt |
| EA EX5 and preset | `BLOCKED_EXTERNAL_INPUT` | Local V26/V63 and Mentor candidates exist, but no operator-approved production target/provenance was specified |

The frozen contract remains unchanged:

```text
BUNDLE_ID=p3-bundle-577e5dfd0702c52c8f5318063703dd616a633704444ba5371e1c74e6dc080c6a
HISTORICAL_REFERENCE_CUTOFF_UTC=2023-12-30T08:00:00Z
PHASE1_DATASET_FINGERPRINT=2dc6dcd74928ed00923fd21f032ba0700f1c9c50459c9e0159872aa2045680ff
CANONICALIZER_FINGERPRINT=0770ab50bf8509df0443468a9e2fbc0d1450b1c0cd167f56d426538f2b916892
```

## Package and attestation

`PRODUCTION_PACKAGE_STATUS=NOT_CREATED`. Package creation correctly remains
blocked until the real frozen index and an operator-approved EA/preset pair are
available. `CHECKSUMS.sha256` inside a package would not be a trusted detached
attestation; therefore `DETACHED_ATTESTATION_STATUS=PENDING_OPERATOR` and no
package digest is claimed.

The test-only suite covers package tamper/missing-artifact refusal, including
model, EX5, index, cutoff, approved-SHA, trusted-digest and missing-artifact
cases. These fixtures are not production artifacts and do not change runtime
state.

## Windows, MT5 and runtime boundary

The current host reports Windows 10 Pro 25H2 build 26200.9457, Python 3.11.9,
PowerShell 7.6.5 Core and Git 2.54.0. It contains the existing checkout,
outputs and MT5 state, so it is not eligible as the clean Windows acceptance
host required by the PRD. No clean Windows host or VM was provided for this
task. Consequently bootstrap, MT5 GUI/account evidence, Scheduler lock/logoff/
reboot behavior and MQL5 compile are `NOT_RUN` or `BLOCKED`; Ubuntu CI and
test-only fixtures cannot substitute for them.

## Test-only evidence and CI reconciliation

The 23 node-operations scenarios plus the existing repository suite passed:

```text
PYTHON_TESTS=86/86 PASS
COMPILEALL=PASS
POWERSHELL_PARSE=PASS
SQLITE_INTEGRITY_FK=PASS_TEST_ONLY
ARTIFACT_INTEGRITY_TESTS=TEST_ONLY_PASS
HANDOFF_STATUS=TEST_ONLY_PASS
BACKUP_STATUS=TEST_ONLY_PASS
RESTORE_DRILL_STATUS=TEST_ONLY_PASS
AGENT_TAKEOVER_STATUS=TEST_ONLY_PASS
EXECUTION_API_PATH_COUNT=0
MQL5_COMPILE=NOT_RUN
GIT_DIFF_CHECK=PASS_AT_EVIDENCE_GENERATION
```

Before this evidence-only update, exact implementation head
`f671f709c5bd9820c8f9de7a3dece9a526e4f379` had all three workflows successful:

```text
PHASE2_CI=SUCCESS; RUN=35092819101
PHASE3_CI=SUCCESS; RUN=35092819103
PHASE3_1_CI=SUCCESS; RUN=35092819102
```

Those results are recorded as historical evidence for that exact SHA. The
evidence commit changes the PR head, so its three CI results must be verified
again on the new exact head before any readiness assessment.

## Remaining blockers

1. Provide an operator-approved clean Windows host or isolated VM and run the
   end-to-end bootstrap and Windows-specific acceptance scenarios.
2. Provide the real frozen `phase3-historical-similarity-index/1` artifact;
   do not rebuild it from `similarity_results.json`.
3. Select and approve the exact production EA EX5/preset pair and provenance.
4. Confirm the resulting package digest or signature through a detached trusted
   channel before marking production package verification PASS.

## Safety stop

```text
DO_NOT_MERGE=YES
DO_NOT_ACTIVATE_FORWARD=YES
DO_NOT_CREATE_PRODUCTION_AUTHORIZATION=YES
DO_NOT_START_SCHEDULER=YES
EXECUTION_AUTHORITY=NONE
TRADE_CONTROL_AUTHORITY=NONE
LIVE_EXECUTION_ENABLED=NO
FORWARD_RUN_ID=NOT_CREATED
READY_FOR_PHASE4=NO
MERGE_READY=NO
```

Evidence timestamp: `2026-09-16T14:48:11.7317021Z`.
