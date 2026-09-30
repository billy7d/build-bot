# APPROVAL A1-R2 — EXECUTION REPORT

Date: 2026-09-24
Evidence directory: `D:\Trading\MT5-GateB-Acceptance-Evidence\A1-R2-20260924T115009Z`

## 1. Elevation

`ADMIN_SESSION=FAILED`

Observed identity: `MSI\CodexSandboxOffline`. Administrator SID membership: `false`; `IsInRole(Administrator)`: `false`; token elevation type: `Default`; `TokenIsElevated`: `false`; integrity level: `Medium Mandatory Level` (`S-1-16-8192`).

The required protected-location write probe was **not run**. A1-R2 requires an immediate hard stop when the token is not elevated. No UAC/ACL workaround was attempted.

Evidence: `elevation.json`.

## 2. Previous failed installation

No R2 revalidation was performed after the elevation check failed. The last A1-R evidence (2026-09-24) recorded `C:\Program Files\MetaTrader 5` as the failed A1 installation, with 583 files, 19 directories, no reparse points, and a complete hash inventory matching its pre-cleanup snapshot. It also recorded that the exact failed terminal PID `21688` had been stopped. Treat these as prior observations, not a fresh R2 snapshot.

## 3. Cleanup

`OFFICIAL_UNINSTALL_R2=NOT_RUN`
`MANUAL_CLEANUP_R2=NOT_RUN`
`REGISTRY_CHANGE_R2=NONE`

The prior A1-R report documents the earlier idle uninstaller attempt and denied manual cleanup. This R2 turn made no uninstall, filesystem, registry, ACL, service, startup, or scheduled-task changes.

## 4. AppData/Common

No R2 inventory or ownership reclassification was performed after the elevation hard stop. The prior A1-R evidence recorded these paths as preserved; their state below is **last-known**, not freshly verified:

| Path | Classification for R2 | Last-known action |
|---|---|---|
| `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075` | `UNKNOWN` — `origin.txt` pointed to the failed root, but runtime binding was not verified | `PRESERVED` |
| `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\bases\Default\History\EURUSD\2023.hcc` | `UNKNOWN` | `PRESERVED` |
| `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\bases\Default\History\GBPUSD\2023.hcc` | `UNKNOWN` | `PRESERVED` |
| `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\bases\Default\History\USDCHF\2023.hcc` | `UNKNOWN` | `PRESERVED` |
| `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\bases\Default\History\USDJPY\2023.hcc` | `UNKNOWN` | `PRESERVED` |
| `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\logs\20260922.log` | `UNKNOWN` | `PRESERVED` |
| `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\Common` | `UNKNOWN` / potentially shared | `PRESERVED_NO_WRITE` |

The five child paths are relative to the first AppData directory. Their ownership was not established, so none is authorized for deletion.

## 5. V26 safety

No R2 V26 pre-cleanup or post-cleanup comparison was run because the session failed the mandatory elevation gate before revalidation or cleanup.

`V26_PRE_CLEANUP_SAFETY=NOT_VERIFIED`
`V26_POST_CLEANUP_SAFETY=NOT_RUN`
`V26_FINAL_SAFETY=NOT_VERIFIED`

Prior A1-R evidence had a corrected comparison reporting 582 files and zero differences, including a post-denied-cleanup-attempt comparison. That prior result is not represented as an R2 verification.

## 6. Installer syntax root cause

No R2 installer execution or syntax revalidation was performed. The previous A1-R report records the old runner's `/path` value being split into three argument elements (`/path:"`, the destination path, and `"`), so the installer did not receive one quoted path argument. The corrected argument construction placed `/path:"D:\Trading\MT5-GateB-Acceptance"` in one argument element, and a non-installing echo probe returned the intended command line. R1 also recorded the MetaQuotes installation documentation as the source for `/auto /path:"..."` syntax.

This is prior evidence only; R2 stopped before its required syntax and installer revalidation. `REINSTALL_BLOCKED=ADMIN_SESSION_NOT_VERIFIED`.

## 7. Reinstall

`REINSTALL_ATTEMPTED=NO`
`INSTALL_ROOT=NOT_REVALIDATED`
`TERMINAL_PATH=NOT_REVALIDATED`
`TERMINAL_SHA256=NOT_VERIFIED`
`TERMINAL_VERSION=NOT_VERIFIED`
`TERMINAL_SIGNER=NOT_VERIFIED`

No installer was launched in R2.

## 8. Wrong-root verification

`WRONG_ROOT_CLEAN=NOT_VERIFIED`
`WRONG_ROOT_RECREATED=NOT_VERIFIED`

The prior A1-R report recorded the wrong root still present. R2 did not recheck it after the elevation gate failed.

## 9. Isolation discovery

No R2 discovery or runtime action was performed. Installation/data-root linkage, Common-root behavior, `/portable`, and `/config` remain unverified for R2.

`RUNTIME_ISOLATION=NOT_VERIFIED`

## 10. Final state

`A1_R2_STATUS=BLOCKED`
`A1_STATUS=BLOCKED`
`ADMIN_SESSION=FAILED`
`V26_SAFETY=NOT_VERIFIED`
`DEDICATED_TERMINAL_INSTALLED=NO`
`WRONG_ROOT_CLEAN=NOT_VERIFIED`
`RUNTIME_ISOLATION=NOT_VERIFIED`
`A2_AUTHORIZED=NO`
`APPROVAL_B_AUTHORIZED=NO`
`TRADING_AUTHORIZED=NO`
`MERGE_READY=NO`
`ACTIVATION_READY=NO`

## 11. A2 readiness recommendation

Do not consider A2. Resume A1-R2 only from a Windows session whose actual process token is elevated (Administrator membership, full elevation, and High integrity level verified). Then perform the mandated fresh pre-cleanup and V26 checks before any modification. This report does not authorize a cleanup retry from the current session.
