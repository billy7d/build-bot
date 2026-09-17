# PR #6 Security Remediation Report

## Evidence identity

| Field | Value |
|---|---|
| `record_type` | `SECURITY_REMEDIATION_IMPLEMENTATION` |
| `repository` | `https://github.com/billy7d/build-bot` |
| `pull_request` | `#6` |
| `reviewed_head_sha` | `3831a65caa0bb231feb7f403bd9bb223cc3614b2` |
| `validated_head_sha` | `75d9ce29fb299958c5e120928b0a91818fd59acf` |
| `ci_head_sha` | `75d9ce29fb299958c5e120928b0a91818fd59acf` |
| `validation_timestamp_utc` | `2026-09-17T14:20:08.9496032Z` to `2026-09-17T14:20:30.0798199Z` |
| `implementation_commit` | `75d9ce29fb299958c5e120928b0a91818fd59acf` |
| `report_scope` | This record validates the implementation commit above. The later report commit and final PR head are recorded separately in versioned external evidence to avoid a self-referential SHA loop. |
| `artifact_manifest_sha256` | `5716b6d753d4f57af35ccf0874df1711853ee44f047893b9d452c61da707b3d7` (read-only historical staging manifest; not used as production attestation) |
| `detached_attestation_status` | `PENDING_OPERATOR` |
| `operator_approval_status` | `PENDING` |

The prior `forward_node_ops_report.md`, `forward_node_ops_status.json`, and
Windows acceptance files were not edited, moved, overwritten, or deleted.
This report is a new implementation record. Final-head evidence for the report
commit is written outside Git under a new versioned acceptance directory.

## Findings and fixes

### P0-01 — Verify before execute and TOCTOU protection

- `root_cause`: The wrapper executed `PackagePath/bootstrap/bootstrap.ps1` when the source checkout was absent, before package verification.
- `affected_files`: `scripts/phase3/bootstrap_forward_node.ps1`, `agent/phase3/node_ops.py`.
- `implemented_fix`: The wrapper now requires an independently provisioned, clean Git checkout, verifies its full `ExpectedGitSha` with Git, and refuses dirty or mismatched source. It never dispatches a script from the package. The generated package script is inert until it hands off to the trusted source. The verifier checks the full package, then revalidates all checksum entries and captures an in-memory byte snapshot before any runtime artifact is used.
- `security_invariant`: No package code runs before detached digest, package checksums, frozen contracts, and approved source identity pass. A package changed after verification is rejected with `PACKAGE_CHANGED_AFTER_VERIFICATION`.
- `test_cases`: `test_wrapper_never_executes_unverified_package_bootstrap`, `test_test_only_tamper_and_snapshot_change_fail_closed`, `test_verified_package_snapshot_is_reused_for_bootstrap_artifacts`, `test_bootstrap_is_idempotent_and_never_creates_auth_or_run`.
- `test_result`: `PASS`.
- `remaining_risk`: A clean Windows node still requires the operator to provision the trusted source checkout from the approved channel; this implementation does not claim that operational provisioning has occurred.

### P0-02 — Isolate `TEST_ONLY` from production

- `root_cause`: A `test_only` manifest could be accepted without detached attestation, and a valid digest could otherwise be interpreted as production trust.
- `affected_files`: `agent/phase3/node_ops.py`, `agent/tests/test_forward_node_ops.py`.
- `implemented_fix`: Added explicit `PackageVerificationMode.PRODUCTION` and `PackageVerificationMode.TEST_ONLY`. Production verification and `bootstrap_forward_node` reject `test_only=true` even with a matching external digest. Only the isolated test mode accepts an unattested fixture, and its status remains test-only. Full SHA, artifact, frozen-contract, and detached-digest checks remain enforced.
- `security_invariant`: `TEST_ONLY` cannot create a production bootstrap, runtime, authorization, run, or scheduler state.
- `test_cases`: `test_package_checksum_and_frozen_artifacts`, `test_production_package_requires_detached_trusted_manifest_digest`, `test_test_only_package_is_allowed_only_in_isolated_verify_mode`, `test_rehashed_test_only_flag_cannot_become_production`, `test_test_only_tamper_and_snapshot_change_fail_closed`.
- `test_result`: `PASS`.
- `remaining_risk`: Test fixtures remain non-production by contract; no fixture is evidence of provenance or live readiness.

### P1-01 — PowerShell command-injection hardening

- `root_cause`: Package generation interpolated repository URL and approved SHA into generated PowerShell source.
- `affected_files`: `agent/phase3/node_ops.py`, `agent/tests/test_forward_node_ops.py`.
- `implemented_fix`: Repository URLs are restricted to HTTPS `github.com` owner/repository paths, full Git SHAs are validated, generated PowerShell contains no caller data, and Git/Python commands use argument arrays with `shell=False` or PowerShell splatting. Git non-zero results stop the flow; no default URL substitution is performed.
- `security_invariant`: Quotes, separators, ampersands, newlines, option prefixes, and unapproved hosts cannot change command structure or execute unintended commands. Windows paths with spaces and Unicode remain data arguments.
- `test_cases`: `test_repository_url_allowlist_rejects_injection_and_invalid_sha`, `test_generated_bootstrap_uses_only_argument_arrays`, `test_wrapper_never_executes_unverified_package_bootstrap`, plus the 30 forward-node scenarios.
- `test_result`: `PASS`.
- `remaining_risk`: Repository allowlisting is intentionally limited to the approved GitHub host; a different hosting provider requires an explicit reviewed policy change.

### P1-02 — Exact-head evidence without rewriting history

- `root_cause`: Existing acceptance reports described an older head and left final-head CI pending.
- `affected_files`: New file only: `reports/trading_agent/phase3_forward_node_ops/security_remediation_report.md`.
- `implemented_fix`: Historical reports remain immutable. This versioned record distinguishes implementation evidence from acceptance, external operator evidence, and exact-head CI. It records the implementation head and the real CI run IDs below. The report commit is deliberately not asserted as its own final head; a separate external record will bind the final PR head to its CI runs.
- `security_invariant`: No CI result is copied from another SHA, branch, or unfinished run.
- `test_cases`: GitHub API verification of the three completed runs, with each run `head_sha` equal to `validated_head_sha`.
- `test_result`: `PASS` for the implementation commit; final report-commit exact-head evidence is recorded separately after push.
- `remaining_risk`: The final PR head changes when this report is committed. It must be rechecked externally before any merge decision.

## Validation evidence for implementation commit

| Check | Result |
|---|---|
| Full unit/integration suite | `PASS` — 93/93, `2026-09-17T14:20:08.9496032Z` to `2026-09-17T14:20:30.0798199Z` |
| Forward node suite | `PASS` — 30/30, `2026-09-17T14:20:09.0467271Z` to `2026-09-17T14:20:24.6011897Z` |
| Python compileall | `PASS` |
| PowerShell parser | `PASS` — 17 scripts |
| JSON validation | `PASS` — 28 files |
| Production execution API scan | `PASS` — no `shell=True` or `Invoke-Expression` in `agent/phase3` or `scripts` |
| Git diff check | `PASS` |
| Activation side effects | `PASS` — no authorization, FORWARD run, scheduler install, terminal launch, or trade command |

## Real GitHub Actions evidence

All three required workflows completed successfully at the exact
`validated_head_sha`:

- [trading-agent-phase2-validation — run 35232999730](https://github.com/billy7d/build-bot/actions/runs/35232999730): `completed / success`.
- [trading-agent-phase3-validation — run 35232999661](https://github.com/billy7d/build-bot/actions/runs/35232999661): `completed / success`.
- [trading-agent-phase3-forward-validation — run 35232999770](https://github.com/billy7d/build-bot/actions/runs/35232999770): `completed / success`.

## Production and operator gates intentionally still pending

```text
DETACHED_ATTESTATION=PENDING_OPERATOR
CLEAN_WINDOWS_APPROVAL=PENDING
V26_EX5_PRESET=NOT_DEPLOYED
FIRST_REAL_OPPORTUNITY=NOT_AVAILABLE
WINDOWS_OPERATIONAL_ACCEPTANCE=PENDING

LIVE_EXECUTION_ENABLED=NO
EXECUTION_AUTHORITY=NONE
TRADE_CONTROL_AUTHORITY=NONE
FORWARD_AUTHORIZATION=NOT_CREATED
FORWARD_RUN_ID=NOT_CREATED
SCHEDULER=NOT_INSTALLED_OR_DISABLED
DO_NOT_ACTIVATE_FORWARD=YES
DO_NOT_MERGE=YES

CODE_REMEDIATION=PASS_FOR_IMPLEMENTATION_COMMIT
OPERATOR_ACCEPTANCE=PENDING
MERGE_READY=NO
ACTIVATION_READY=NO
```
