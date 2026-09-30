# APPROVAL A1-R3 — Operator-Assisted Recovery Handoff

Date: 2026-09-24
Status: `A1_R3_WAITING_OPERATOR_EXECUTION`

## 1. Privilege boundary

`CODEX_TOKEN=NON_ADMIN`
`IDENTITY=MSI\CodexSandboxOffline`
`ADMIN_GROUP_MEMBER=NO`
`TOKEN_ELEVATED=NO`
`INTEGRITY_LEVEL=MEDIUM`
`PRIVILEGED_ACTION=NOT_RUN_OPERATOR_EXECUTION_REQUIRED`

No UAC/elevation attempt, ACL or ownership change, cleanup, registry modification, installer launch, or reinstall was performed. The existing A1, A1-R, and A1-R2 reports/evidence were left intact.

## 2. R3.1 preflight

The failed installation at `C:\Program Files\MetaTrader 5` still matches the saved A1-R fingerprint: 583 files, 19 directories, no reparse points, and manifest SHA-256 `AA6FC32521EE4BECB29317FB21A476F837E0B4EE7C54397431E55154F48FFB1C`. The terminal is version `5.0.0.6182`, SHA-256 `F61ECFAD618A4577DF6743EB10E21CFEB2C374EA66BA8D4813C2C0CCCA784D33`, with a valid MetaQuotes signature. The registered uninstaller also matches the saved SHA-256 and has a valid signature. The uninstall registration points to this exact failed root.

`D:\Trading\MT5-V26` matches its protected baseline: 582 files and zero additions, removals, hash/size changes, or timestamp changes. Its uninstall registration points to V26. The approved destination `D:\Trading\MT5-GateB-Acceptance` is absent. The failed installation and V26 preflight checks pass; this does not substitute for the required post-cleanup V26 comparison.

The non-admin token cannot read process, service, scheduled-task, or startup-command inventories (four `Access denied` results). The registry Run-key scan found zero references to the failed root. No assertion is made that no process is currently running; the elevated dry-run must complete those checks.

One inherited R1 metadata inconsistency was retained and documented rather than rewriting prior evidence: a derived flag says `wrong_root_created_after_a1_start=false`, while the exact timestamps show creation 44.570 seconds after install start. The exact timestamps, live creation time, and saved inventory agree. The cleanup script records this as an audit warning and checks exact timestamps/fingerprint rather than trusting the contradictory derived flag.

## 3. Cleanup package and sandbox dry-run

Script: [gate_b_a1_cleanup_admin.ps1](/D:/Trading/buildbot/tools/gate_b_a1_cleanup_admin.ps1)
SHA-256: `B796894C7F9969C9BFC615CDC912F9F4AC8331FA2BB09CB39C97BD4435943BA4`
PowerShell parser: `PASS`

The script accepts exactly one of `-DryRun` or `-Execute`; the target is fixed to `C:\Program Files\MetaTrader 5`. It checks the complete failed-root fingerprint, registry ownership, V26 baseline, canonical paths and reparse points. It checks processes/services/tasks/startup references and aborts if those reads fail, if the failed terminal is active, or if references are found. Execute mode repeats those system-reference checks immediately before removal, revalidates the target/V26/registry, exports the exact uninstall key before removing it, and only removes the exact failed tree and exact matching uninstall key. It does not stop processes by image name or modify ACLs/ownership. AppData and `Common` are explicitly preserved. Evidence write failure or any safety mismatch is non-success.

Sandbox dry-run at `2026-09-24T16:17:37Z`:

```text
ADMIN_REQUIRED
TARGET_FINGERPRINT=PASS
V26_PRE_R3=PASS
ADMIN_READ_CHECKS_DEFERRED count=4
DRY_RUN_CORE_CHECKS=PASS
DRY_RUN_STATUS=INCOMPLETE_ADMIN_READ_CHECKS
SCRIPT_EXIT_CODE=20
```

This is a core/read-only pass, **not** the full required dry-run pass. No action was performed. Operator must run the elevated dry-run and receive exit code 0 plus `DRY_RUN_STATUS=PASS` before `-Execute` is allowed.

Preparation records are in [the workspace evidence folder](/D:/Trading/buildbot/outputs/gate_b_a1_r3_preparation_20260924) and copied to `D:\Trading\MT5-GateB-Acceptance-Evidence\A1-R3-Preparation-20260924T161737Z`. Both locations contain `r3-preflight.json`, `sandbox-dryrun.json`, `installer-syntax-analysis.md`, `cleanup-script-sha256.txt`, the report, and the preserved installer echo probe.

## 4. Operator handoff

In a 64-bit Windows PowerShell window opened with **Run as Administrator**, first verify the script hash:

```powershell
$scriptPath = 'D:\Trading\buildbot\tools\gate_b_a1_cleanup_admin.ps1'
Get-FileHash -LiteralPath $scriptPath -Algorithm SHA256
```

Proceed only if it prints the exact SHA-256 above. Then run the dry-run:

```powershell
& $scriptPath -DryRun
$LASTEXITCODE
```

Only if the output includes `DRY_RUN_STATUS=PASS`, has exit code `0`, and contains no error/warning requiring investigation, run:

```powershell
& $scriptPath -Execute
$LASTEXITCODE
```

Expected successful execution markers:

```text
WRONG_ROOT_CLEAN=YES
V26_POST_R3_CLEANUP=PASS
CLEANUP_STATUS=PASS
```

The elevated dry-run writes `cleanup-admin-result.json` and `cleanup-admin.log.txt` under `D:\Trading\MT5-GateB-Acceptance-Evidence\A1-R3-DryRun-<UTC timestamp>`. Execute writes those files and the exported registry backup `failed-install-uninstall-entry.reg` under `D:\Trading\MT5-GateB-Acceptance-Evidence\A1-R3-<UTC timestamp>`. Return the actual output, exit codes, and evidence directory paths to Codex. On any non-pass, stop; do not run the next phase or reinstall.

## 5. Installer syntax

MetaQuotes documents `/auto /path:"..."` for unattended installation and a custom destination. The previous runner split the `/path` option and quote boundaries across three `Start-Process -ArgumentList` elements. Microsoft documents that the array is joined into one space-separated string, so the split construction inserted spaces within the quoted path value. The preserved non-installing echo probe showed the corrected command as `/auto /path:"D:\Trading\MT5-GateB-Acceptance"`, with `/auto` and the entire `/path:"..."` value as two array items. The corrected PowerShell form and source links are recorded in `outputs/gate_b_a1_r3_preparation_20260924/installer-syntax-analysis.md`.

`INSTALLER_ARGUMENT_SYNTAX=VERIFIED`
`INSTALLER_LAUNCHED=NO`
`INSTALLER_INTEGRITY=RECHECK_REQUIRED_BEFORE_REINSTALL`

Before any reinstall, recheck the installer hash/signature/signer/version. Reinstall remains gated on Operator cleanup plus Codex's independent verification that the failed root is absent and V26 is unchanged.

## 6. State and stop boundary

`A1_R3_STATUS=WAITING_OPERATOR`
`A1_STATUS=BLOCKED`
`V26_PRE_R3=PASS`
`V26_POST_R3_CLEANUP=NOT_RUN`
`V26_FINAL=NOT_VERIFIED`
`V26_SAFETY=NOT_VERIFIED`
`WRONG_ROOT_CLEAN=NO`
`DEDICATED_TERMINAL_INSTALLED=NO`
`RUNTIME_ISOLATION=NOT_VERIFIED`
`A2_AUTHORIZED=NO`
`APPROVAL_B_AUTHORIZED=NO`
`TRADING_AUTHORIZED=NO`
`ACTIVATION_READY=NO`

Stop here for the Operator's Administrator action. After the evidence is returned, Codex must independently inspect the failed root and V26 before considering the single authorized A1 reinstall. Stop before A2.
