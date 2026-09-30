# APPROVAL A1 — EXECUTION REPORT

## 1. Decision

`APPROVAL_A1=GRANTED`

Scope executed: dedicated MT5 installation and installation-level verification only.

## 2. Installation

`INSTALL_STATUS=FAIL`

Preflight passed. The installer exited with code `0`, but the approved target was not created. The run therefore failed the exact-root requirement and was hard-stopped without retry.

Requested command:

```text
D:\mt5setup.exe /auto /path:"D:\Trading\MT5-GateB-Acceptance"
```

The first runner passed the `/path` value as three argument elements (`/path:"`, the path, and `"`), so the installer ignored the requested custom root and created an unapproved default installation instead. The runner was corrected in the repository after the hard-stop; the installer was not run again.

## 3. Installer verification

All pre-install checks passed against `D:\mt5setup.exe`:

- SHA-256: `F15EEAE5E46DB7E94AFC2786C059266107E4AAED663B3318AFD4A3FC86D4F972` — `VERIFIED`
- Size: `23,312,784` bytes — `VERIFIED`
- File version: `5.0.0.5908` — `VERIFIED`
- Authenticode: `Valid` — `VERIFIED`
- Signer: `MetaQuotes Ltd.` — `VERIFIED`

## 4. Terminal verification

Approved root:

```text
D:\Trading\MT5-GateB-Acceptance\       NOT_CREATED
D:\Trading\MT5-GateB-Acceptance\terminal64.exe  NOT_VERIFIED
```

Unexpected unapproved installation created by the installer:

```text
C:\Program Files\MetaTrader 5\
C:\Program Files\MetaTrader 5\terminal64.exe
```

Observed binary identity at the unapproved root:

- SHA-256: `F61ECFAD618A4577DF6743EB10E21CFEB2C374EA66BA8D4813C2C0CCCA784D33`
- File/product version: `5.0.0.6182`
- Authenticode: `Valid`
- Signer: `MetaQuotes Ltd.`

The observed terminal is not treated as the acceptance terminal. A `terminal64.exe` process remains at that unapproved path (`PID 21688`, started `2026-09-22T14:39:38.4002518Z`). Its command line could not be read (`Access denied`). It was not stopped because A1 permits safe closure only after verifying ownership of the dedicated acceptance process; no broad or unapproved process termination was performed.

## 5. Isolation

| Item | Result |
|---|---|
| Dedicated installation root | `D:\Trading\MT5-GateB-Acceptance` — `NOT_CREATED` |
| Dedicated data root | `NOT_VERIFIED_A1_NO_RUNTIME_LAUNCH` |
| Unapproved data-root candidate | `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075` — discovered after the failed install; runtime binding `NOT_VERIFIED` |
| Common data root | `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\Common` exists; acceptance namespace/write isolation `NOT_VERIFIED` |
| Terminal identity | File identity verified only for the unapproved root; runtime identity `NOT_VERIFIED` |

`ISOLATION_PENDING_A2` remains the correct classification. No acceptance data was written to the common root, and no portable/config/runtime test was performed.

## 6. V26 safety

Protected root: `D:\Trading\MT5-V26`.

The pre-install manifest contained 582 files. A corrected direct comparison against the post-observation manifest found:

```text
added files       = 0
removed files     = 0
hash changes      = 0
size changes      = 0
timestamp changes = 0
V26_SAFETY        = VERIFIED_UNCHANGED_AT_POST_OBSERVATION
```

The first post-observation collector emitted a false modified-file list because of a comparator defect; that raw result is preserved and superseded by `v26-comparison-corrected.json`. No V26 cleanup, rollback, overwrite, or configuration change was performed.

## 7. Tests and evidence

Evidence root:

`D:\Trading\MT5-GateB-Acceptance-Evidence\A1-20260922T143827Z-9bd4b22e`

Key evidence:

- `preflight.json` — installer, roots, free space, process snapshot, and V26 preflight.
- `v26-baseline-before.json` — 582-file protected-root baseline.
- `installation.json` — exact runner invocation, timestamps, exit code, and missing approved target.
- `hard-stop-observation.json` — unexpected default installation and process identity.
- `v26-baseline-after-observation.json` — post-observation protected-root manifest.
- `v26-comparison-corrected.json` — corrected unchanged result.
- `post-hard-stop-mapping.json` — data-root/common-root and startup/process mapping.
- `a1-summary.json` — machine-readable execution summary.

Results:

- Installer integrity: `VERIFIED`
- Exact approved installation root: `FAILED`
- Unapproved default installation detected: `FAILED`
- V26 unchanged at post-observation: `VERIFIED`
- Dedicated data-root isolation: `NOT_VERIFIED`
- Common-root isolation: `NOT_VERIFIED`
- Startup/scheduled-task checks: `NOT_VERIFIED` where the host returned access/provider errors
- Login, EA attach, chart execution, AutoTrading, trading, FORWARD, Gate B runtime, and A2 actions: `NOT_APPLICABLE` / not performed

## 8. Blockers

1. The approved installation root was not created.
2. The installer created `C:\Program Files\MetaTrader 5`, outside A1 scope.
3. The unapproved `terminal64.exe` process (`PID 21688`) remains running; its command line is not readable, and it was intentionally not terminated.
4. The installer argument handling defect must be reviewed before any future attempt. No retry was performed.
5. Data-root, common-root, startup, and runtime identity remain unverified.

## 9. Final status

`A1_STATUS=BLOCKED`

`A2_AUTHORIZED=NO`

`APPROVAL_B_AUTHORIZED=NO`

`TRADING_AUTHORIZED=NO`

`MERGE_READY=NO`

`ACTIVATION_READY=NO`

## 10. Recommendation for next approval

Operator review is required before any further action. In particular, decide how to handle the unapproved `C:\Program Files\MetaTrader 5` installation and its running process. Do not delete, move, update, or stop it through this A1 run. Any future installation attempt needs a separately reviewed corrected invocation and must re-run the complete preflight; A2 and Approval B remain unauthorized.
