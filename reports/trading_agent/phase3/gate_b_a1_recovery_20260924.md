# OPERATOR DECISION A1-R — Recovery Execution Report

Date: 2026-09-24
Status: `BLOCKED_NEEDS_ELEVATED_WINDOWS_ADMIN_ACTION`

## Outcome

Recovery was carried through exact process identification, termination, installer verification, and cleanup preflight. It did not reach a clean installation state. The unauthorized default root still exists, so the approved installer was not retried. A2, login, EA attachment, AutoTrading, trading, and runtime acceptance checks were not started.

## Failed-install process and uninstaller

- PID `21688` was re-verified immediately before termination: executable `C:\Program Files\MetaTrader 5\terminal64.exe`, owner `MSI\billy`, start time `2026-09-22T14:39:38.4002518Z`, SHA-256 `F61ECFAD618A4577DF6743EB10E21CFEB2C374EA66BA8D4813C2C0CCCA784D33`, valid MetaQuotes signature. Only that exact PID was stopped; it exited. No MT5-V26 process was present before or after.
- The registered `C:\Program Files\MetaTrader 5\uninstall.exe` was confirmed to be the MetaQuotes-signed binary registered for that root and launched without guessed arguments. PID `19860` remained idle, had no window or child process, and showed no CPU progress over six seconds. The computer-use UI could not initialize, so the uninstaller could not be driven interactively. PID `19860` was then re-verified and stopped exactly.

## Cleanup and data preservation

The failed root was inventoried and SHA-256 checked: 583 files, 19 directories, no reparse points. Immediately before cleanup, its complete path/size/hash inventory still matched the saved pre-cleanup inventory. The matching uninstall registry entry was exported to a backup before cleanup.

The controlled removal attempt was denied by Windows at `C:\Program Files\MetaTrader 5\Bases\Default\History\EURUSD\2023.hcc`. The active token is `MSI\billy` and is not in the local Administrators group. A post-attempt full hash comparison confirmed no partial change: all 583 files and 19 directories remain, with no additions, removals, or hash/size changes. The matching uninstall registry entry remains in place. No privilege/ACL changes were attempted.

The related data directory `C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075` was preserved. It contains 1,165 files; five paths were newly observed since the initial A1-R scan (four history files and one log). Their origin was not inferred, and none were deleted. The shared `Common` directory was not modified.

## Protected V26 and install preflight

`D:\Trading\MT5-V26` passed a full comparison after the denied cleanup attempt: 582 files, zero additions/removals, zero hash/size/timestamp changes. Its uninstall registration still points to `D:\Trading\MT5-V26`.

The approved installer remains verified at `D:\mt5setup.exe` (SHA-256 `F15EEAE5E46DB7E94AFC2786C059266107E4AAED663B3318AFD4A3FC86D4F972`, valid MetaQuotes signature). `D:\Trading\MT5-GateB-Acceptance` does not exist; its parent is not a reparse point and has about 239 GB free. The corrected argument construction was checked with a non-installing echo probe. These checks do not authorize retry while the wrong root remains.

## Evidence

Evidence directory: `D:\Trading\MT5-GateB-Acceptance-Evidence\A1-R-20260924T105432Z-c04f088c`

- `process-stop.json` — exact failed terminal PID stop and V26 process snapshots.
- `pre-cleanup.json` — complete wrong-root and related-data inventories plus registration and installer observations. Its embedded V26 timestamp counter used the earlier faulty comparator; the separately saved corrected comparisons below supersede it.
- `manual-cleanup-preflight.json` — exact root inventory match and related-data path-set observation.
- `wrong-terminal-uninstall-entry-backup.reg` — exported matching uninstall registration.
- `cleanup-blocker.json` — access-denied condition, current token, and unchanged safety boundaries.
- `v26-before-cleanup-comparison-corrected.json` — original A1 baseline to A1-R pre-cleanup comparison (`PASS`).
- `v26-after-cleanup-attempt-comparison.json` — A1-R pre-cleanup to post-attempt comparison (`PASS`).
- `installer-argument-probe.txt` — non-installing argument-quoting probe.

## Gate decision

`A1R_STATUS=BLOCKED`
`WRONG_ROOT_CLEANUP=NOT_COMPLETED`
`REINSTALL=NOT_RUN`
`V26_SAFETY=VERIFIED_UNCHANGED`
`A2_AUTHORIZED=NO`
`TRADING_AUTHORIZED=NO`

Continuation requires an Administrator Windows token to complete only the authorized cleanup (or a working interactive Windows UI for the registered uninstaller). Then verify the wrong root and stale registration are absent, revalidate V26, and perform at most the single approved reinstall. Preserve the related AppData tree and `Common`; stop immediately if installation lands anywhere other than `D:\Trading\MT5-GateB-Acceptance`.
