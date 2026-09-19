# MT5 V26/V63 automatic telemetry recovery report

Generated: 2026-09-18 (Asia/Saigon), read-only investigation and implementation
on the Windows host. This report is separate from the 2026-09-17 acceptance
artifacts and does not modify them.

## Evidence and recovery result

**V26_ROOT_CAUSE:** `PROCESS_ABSENT` in the current WMI process snapshot. The
historical “Algo Trading error before shutdown” note is not independently
confirmed from a timestamped V26 journal/Experts log available to this run;
therefore no causal claim is made and recovery is hard-stopped.

**V63_ROOT_CAUSE:** `PROCESS_ABSENT` in the current WMI process snapshot. No
independent V63 OnDeinit/process-exit evidence was available to attribute a
different cause; recovery is hard-stopped.

**V26_PROCESS_BEFORE:** No `terminal64.exe` process returned by a read-only
`Win32_Process` query. Exact executable exists at
`D:\\Trading\\MT5-V26\\terminal64.exe`.

**V26_PROCESS_AFTER:** Not started. `UNSAFE_TO_RESTART`: approved EX5/preset
hashes and trading-disabled/EA identity attestations are not present, and no
approved launch argument set exists.

**V63_PROCESS_BEFORE:** No `terminal64.exe` process returned by the same
read-only query. Exact executable exists at
`D:\\Trading\\MT5-V63\\terminal64.exe`.

**V63_PROCESS_AFTER:** Not started for the same independent safety gates; V63
was not allowed to affect V26’s decision.

**V26_RECOVERY_ACTION:** `NONE (HARD_STOP_UNSAFE_TO_RESTART)`.

**V63_RECOVERY_ACTION:** `NONE (HARD_STOP_UNSAFE_TO_RESTART)`.

**V26_EX5_SHA256:** `NOT_AVAILABLE_NOT_DEPLOYED` (expected
`Phase3CanonicalCandidate.ex5` is absent).

**V63_EX5_SHA256:** `NOT_AVAILABLE_NOT_DEPLOYED` (expected
`Phase3CanonicalCandidate.ex5` is absent).

**V26_PRESET_SHA256:** `NOT_AVAILABLE_NOT_DEPLOYED` (expected
`phase3-canonical-v26-telemetry.set` is absent).

**V63_PRESET_SHA256:** `NOT_AVAILABLE_NOT_DEPLOYED` (expected
`phase3-canonical-v63-telemetry.set` is absent).

**V26_HEARTBEAT:** `NOT_VERIFIED`; no approved EA heartbeat attestation.

**V63_HEARTBEAT:** `NOT_VERIFIED`; no approved EA heartbeat attestation.

**V26_TELEMETRY:** `NOT_VERIFIED`; common primary
`phase3-opportunity-observation.jsonl` is absent and no real record was
created.

**V63_TELEMETRY:** `NOT_VERIFIED`; the same primary source is absent. A shared
file is never treated as evidence for both instances.

**REAL_OPPORTUNITY:** `PENDING`; no synthetic opportunity was created.

## Watchdog

**WATCHDOG_IMPLEMENTATION:** `agent/phase3/mt5_watchdog.py` plus
`scripts/phase3/mt5_watchdog.ps1`. The module performs exact process identity,
artifact SHA-256, profile/data-directory, EA/account/server, trading-disabled
attestation, JSONL schema, timestamp/age, source identity and sequence checks.
Only an absent terminal with every gate proven can be started; a running
terminal is never duplicated and a stale EA is not removed/re-added.

**WATCHDOG_TEST:** Isolated safety suite `agent.tests.test_mt5_watchdog` passed
10/10. It covers absent/running/duplicate processes, AutoTrading ON,
wrong artifact/account/server, sequence gaps, malformed state and the
persistent circuit breaker. Full repository regression is pending final CI.

**WATCHDOG_INSTALL_STATUS:** `NOT_INSTALLED_OR_DISABLED`. `start`/`stop` are
report-only commands; no Scheduled Task/service was registered.

**RESTART_ATTEMPTS:** `V26=0`, `V63=0`; no terminal was launched.

**CIRCUIT_BREAKER:** Persistent outside Git, maximum 2 attempts per instance in
30 minutes; malformed state blocks recovery. Not opened on this host because
the preflight gates failed first.

**DATA_INTEGRITY:** `PASS_FOR_INVESTIGATION`. No telemetry, JSONL, database,
checkpoint, handoff or backup was truncated, reset, overwritten or merged.
Pre-launch snapshots (when eligible) contain metadata only.

**TRADING_PERMISSION:** `UNVERIFIED => HARD_STOP`. AutoTrading was not enabled;
no order/position API is imported or called by the watchdog.

**TEST_RESULT:** `PASS` for the isolated watchdog suite; full Phase 1/2/3,
PowerShell parse, JSON validation and `git diff --check` are required before
merge.

**CI_RESULT:** `PENDING` until the branch is pushed and exact-head CI runs.

**COMMIT:** `c481976` (watchdog implementation) + `9a45145` (explicit health-state classifications).

**PUSH_STATUS:** `SUCCESS` — branch `codex/mt5-v26-v63-recovery-watchdog` pushed to `origin`.

**PR_URL:** https://github.com/billy7d/build-bot/pull/new/codex/mt5-v26-v63-recovery-watchdog
(branch targets PR #6’s forward-node operations line; no merge is performed).

## Remaining blockers

1. Operator must provide and independently approve the exact EX5/preset files
   and SHA-256 values for each instance.
2. Operator must provide timestamped read-only attestations proving
   AutoTrading/terminal/MQL trading permissions are disabled and proving EA
   attachment, OnInit, account, server, symbol and timeframe separately for
   V26 and V63.
3. Operator must provide explicit, reviewed launch arguments and a verified
   interactive Windows session. No credentials or server overrides may be
   passed on the command line.
4. MT5 journal/Experts logs and a real primary telemetry record are still
   required. Until then `MARKET_TELEMETRY=PENDING_MARKET_DATA` and
   `REAL_OPPORTUNITY=PENDING` remain in force.
5. Persistent watchdog installation at boot/logon requires separate operator
   approval and is intentionally not automated by this change.

System safety remains:

```text
LIVE_EXECUTION_ENABLED=NO
EXECUTION_AUTHORITY=NONE
TRADE_CONTROL_AUTHORITY=NONE
FORWARD_AUTHORIZATION=NOT_CREATED
FORWARD_RUN_ID=NOT_CREATED
AUTO_TRADING=OFF
DO_NOT_MERGE=YES
DO_NOT_ACTIVATE_FORWARD=YES
```
