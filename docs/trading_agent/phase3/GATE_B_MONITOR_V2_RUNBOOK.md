# PR #6 Gate B Permission Monitor V2 Runbook

Status: `PREPARED_OFFLINE_NOT_AUTHORIZED_NOT_EXECUTED`

This runbook covers the PRD implementation, offline validation and approval
boundary only. It is not a deployment, telemetry, trading, FORWARD, Scheduler,
Gate C, merge or activation approval. No second terminal, login, MetaEditor
compile, MT5 launch, chart attach or process stop is performed by this runbook.

## Current capability result

The observed native computer-use state is `apps=[]`; only browser surfaces are
available. An empty native-app inventory is treated as no desktop authority,
not as implicit MT5 access.

```text
GUI_AUTOMATION_AVAILABLE=NO
DEDICATED_TERMINAL_ROOT=D:\Trading\MT5-GateB-Acceptance; NOT_CREATED
PORTABLE_MODE_SUPPORT=IMPLEMENTED_OFFLINE_UNVERIFIED_RUNTIME
DATA_ROOT_ISOLATION=NOT_PROVEN
FILE_COMMON_ISOLATION=NOT_PROVEN; EXPLICIT_ACCEPTANCE_NAMESPACE_REQUIRED
AUTOMATED_COMPILATION=IMPLEMENTED_PLAN_ONLY; BLOCKED_UNAUTHORIZED
SUPPORTED_LAUNCH_METHOD=DOCUMENTED_PORTABLE_CONFIG_LAUNCH; NOT_AUTHORIZED
SUPPORTED_ATTACH_METHOD=NONE
INDEPENDENT_STOP_CAPABILITY=IMPLEMENTED_DUMMY_PROCESS_ONLY
REAL_MT5_FEASIBILITY=NOT_PROVEN
FULL_AUTOMATION_FEASIBLE=NO
MONITOR_PREFLIGHT=BLOCKED
REAL_TELEMETRY=NOT_RUN
INSTALLER_PATH=D:\mt5setup.exe
INSTALLER_SHA256=F15EEAE5E46DB7E94AFC2786C059266107E4AAED663B3318AFD4A3FC86D4F972
INSTALLER_SIGNATURE=AUTHENTICODE_VALID; PUBLISHER=MetaQuotes Ltd.
INSTALLER_VERSION=5.0.0.5908
INSTALLER_CUSTOM_PATH_SUPPORT=OFFICIAL_DOCS_/auto_/path; FILE_SPECIFIC_RUNTIME_NOT_EXECUTED
```

The Python controller, startup generator and process supervisor are available
for an authorized fixture, but the current control surface cannot create or
own a native chart. A manual attach or manual countdown is not relabeled as
automation.

## Architecture decision

### A. Existing shared terminal — rejected

`D:\Trading\MT5-V26` is a shared production-adjacent runtime and is not an
acceptable unattended acceptance target. A process-wide stop could affect
unrelated EAs, and the current surface cannot bind a stop to the exact
terminal process, chart ID, owner token and monitor session. The shared root is
protected by the provisioner and process supervisor; no write, launch or stop
is allowed by this offline implementation.

### B. Dedicated isolated terminal — only candidate, still conditional

The proposed root is:

```text
installation_root = D:\Trading\MT5-GateB-Acceptance
data_root         = same as installation root in portable mode (verify at runtime)
common_root       = existing shared FILE_COMMON scope; no acceptance writes
evidence_root     = D:\Trading\MT5-GateB-Acceptance-Evidence\<session>
```

The provisioner performs read-only checks for existence, overlap with V26,
permissions, free space, existing processes and evidence-root separation. An
existing target blocks; it is never overwritten. Creating an empty layout is
itself approval-gated and was not done. `D:\mt5setup.exe` is now an exact
local installer candidate with a valid MetaQuotes Authenticode signature and
the SHA above. Its download provenance is not established and its behavior has
not been executed. The official installer documentation describes
`/auto /path:"<directory>"`; A1 must explicitly authorize this method and
runtime verification must still prove the actual result.

Portable mode is encoded as a startup contract, not treated as a proof. After
an authorized launch, the actual data directory, profiles, charts, Experts,
configuration and journals must be verified. `FILE_COMMON` must either be
separately collision-free or the monitor must use a dedicated acceptance
namespace; common-file separation is currently `NOT_PROVEN`.

The operator may perform a one-time Investor login in the isolated terminal.
Credentials must not be copied into Git, startup INI, command-line arguments,
controller configuration or evidence. The controller consumes only the
resulting non-secret account/server identity.

## Required approval order

### A1 — isolated environment feasibility

A1 must identify and approve the exact verified provisioning source, the
`D:\Trading\MT5-GateB-Acceptance` installation root, the portable data-root
expectation, the shared `FILE_COMMON` no-write policy, the external evidence
root, rollback and the bounded dummy-process proof. A1 may provision the
dedicated environment after approval, but it does not authorize MT5 launch,
MetaEditor, MQL5 compile, EA attach, Investor login, trading or the 600-second
Gate B session.

A1 PASS requires source integrity, no overlap with V26, actual installation/
data separation, common-file check, external evidence, exact dummy-process
ownership/stop and rollback evidence. A1 FAIL/BLOCKED stops the sequence.

### A2 — MT5 control feasibility

A2 is a separate exact authorization and requires A1 PASS. It may launch only
the named dedicated executable, verify `/portable` + `/config` against the
installed build, prove actual process/data-root identity, verify one owned
`BTCUSD,H1` chart if explicitly included, exercise the exact independent stop
and preserve evidence. It is a short bounded feasibility test, not the full
Gate B session.

A2 does not include MQL5 compile/load/attach by implication. If the optional
MQL5 extension is approved, the exact V2 source SHA, compiler path/version/SHA,
post-compile EX5 hash gate, account/permission scope, short runtime, stop and
rollback must be recorded before execution. No attach occurs before the EX5
hash is explicitly approved. Approval B remains separate after A2 PASS.

### Approval B — one V2 acceptance

Approval B is allowed only after A1 and A2 have produced successful evidence.
It must bind the exact V2 source/EX5 hashes, dedicated executable and data-root
identity, startup-config hash, expected account/server if login is authorized,
chart/session, 600-second window, 540-second stop request, supervisor, stop
and evidence root. There is no retry or extension.

### Approval C — production telemetry

Production EX5/preset deployment, production-EA stop, account-history
reconciliation and real telemetry remain a separate approval. Monitor V2 does
not stop another EA and no production action is implied here.

## Startup and compile contract

The offline startup generator emits a credential-free configuration using:

```text
terminal64.exe /portable /config:<dedicated-config.ini>
[StartUp]
Expert=PR6_ReadOnlyPermissionMonitor_V2
Symbol=BTCUSD
Period=H1
[Experts]
Enabled=1
AllowLiveTrading=0
AllowDllImport=0
Account=0
Profile=0
```

The exact installed MT5 behavior must be verified after authorization because
invalid startup values can fall back to defaults. Runtime PASS requires proof
of the expected executable, actual data root, monitor loaded, exactly one
acceptance chart, `BTCUSD,H1`, correct account/server, no unexpected EA and no
profile fallback. If any item is wrong, stop and classify `STARTUP_CONFIG_VALID`
as `FAIL`; do not retry with alternate settings.

The compiler module prepares the MetaEditor invocation and validates a real
compiler log, zero errors/warnings, expected EX5 output, source SHA and EX5
SHA. It is approval-gated and has not run. A source review or historical V1 EX5
is not a V2 compile result.

Read-only host observation found MT5/MetaEditor build `5.0.0.6182`. The shared
terminal SHA-256 values are recorded in the consolidated Approval A request as
candidate identities only; they do not make the shared installation a
dedicated source. No verified installer/media source was found in the
repository or `D:\Trading` top-level. No dedicated startup INI or V2 EX5
exists, so their hashes remain `PENDING_RUNTIME_ARTIFACT` and
`NOT_AVAILABLE_NOT_COMPILED` respectively.

## Canonical future session

The future authorized session has exactly:

```text
monitor source  = PR6_ReadOnlyPermissionMonitor_V2.mq5
chart           = one newly owned BTCUSD,H1 chart
session         = one unique session, no retry or extension
sampling        = initial snapshot plus one sample every 60 seconds
gap             = no within-session gap over 90 seconds
soft stop       = request by 540 monotonic seconds
hard deadline   = 600 monotonic seconds
trading         = disabled; no order/trading API
```

The supervisor clock begins no later than the authorized launch action and is
independent of EA timer counts and wall-clock changes. Actual attachment time
is recorded separately. Account/server/DEMO status, connection, permission,
symbol/timeframe, duplicate session, heartbeat and sampling failures stop the
run; no automatic reattach or retry is allowed.

## Independent stop and cleanup

The supervisor must be started before launch and must continue as a separately
running local process if the Codex conversation disconnects. It verifies the
exact process identity before every action and refuses shared V26 paths,
numeric-PID-only termination, terminal-wide termination and mismatched
creation/session/data-root identities.

The four facts remain separate:

```text
SELF_STOP_REQUESTED        = EA emitted ExpertRemove/stop request only
EA_REMOVAL_CONFIRMED       = independent exact-chart removal/deinit proof
CHART_CLOSURE_CONFIRMED    = independent proof that the owned chart is closed
INDEPENDENT_STOP_AVAILABLE = separately running supervisor can stop the exact
                              dedicated process/session
```

The offline harness proves graceful timeout followed by authorization-gated
emergency termination against harmless dummy processes, wrong-target rejection,
creation-identity mismatch, shared-V26 protection and 540/600-second deadline
logic. It does not prove the same mechanism against MT5. A journal-only
watchdog is observation, not a stop mechanism. `ExpertRemove()` is a request,
not removal proof. Emergency process exit is not proof of graceful EA removal
or chart closure.

At 540 seconds the supervisor requests graceful stop and records the reason. It
waits only within a bounded grace period. At 600 seconds it may terminate only
the exact, separately authorized dedicated process, then verifies actual exit.
If identity, removal, chart closure or process exit cannot be proven, the
corresponding result is `FAIL`, `INCONCLUSIVE` or `BLOCKED`; never PASS.

## Evidence and failure rules

Every authorized run receives a new evidence root outside the repository,
install root and data root. Preserve original journals, compiler output,
source/EX5/config/terminal hashes, process/chart/session identity, account and
server, UTC and monotonic boundaries, heartbeats, stop decisions, removal,
chart closure, process exit and a SHA-256 manifest. Never store passwords or
tokens; never truncate or rewrite historical evidence.

The evaluator separates installation/data/common isolation, source/binary
identity, startup, launch/attach, session uniqueness, Investor permissions,
sampling, self-stop, independent stop, duration, removal, chart closure,
process termination, production unchanged and evidence integrity. Offline or
dummy PASS cannot become `MONITOR_PREFLIGHT=PASS`; with no real authorized
session the result remains `NOT_RUN`/`BLOCKED`, `GATE_B_OVERALL=BLOCKED`.

## Remaining operator actions

The following are intentionally not performed by this implementation:

- record the A1 decision and supply the verified provisioning source/hash;
- confirm the portable data-root choice, shared `FILE_COMMON` no-write policy,
  external evidence root and rollback scope;
- after A1 PASS, record a separate A2 decision for the short MT5 control test;
- if desired, explicitly authorize the optional MQL5 compile/attach extension
  and its post-compile EX5 hash gate;
- perform any Investor login without exposing credentials;
- after A1/A2 PASS, issue separate Approval B for one real V2 run.

Until those records exist, the correct action is to remain blocked. Do not
create a terminal, launch MT5, compile/attach V2, stop any terminal, run
production telemetry, start FORWARD/Scheduler, run Gate C, merge or activate.
