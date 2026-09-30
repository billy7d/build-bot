# PR #6 Narrow Gate B Monitor Contract Amendment Proposal

Status: `PROPOSAL_NOT_APPROVED`

Proposal ID: `PR6-GATE-B-MONITOR-V2-20260921`

This proposal does not change the approved source SHA, package, V1 monitor,
historical evidence, production EA/preset, Gate C policy, merge state or
activation state. It does not accept or erase the old procedural failures.

## Existing evidence preserved

- V1 functional observations: 27 consistent permission samples.
- V1 procedural failures: two charts, a 21m21.669s session, a 98.736s
  inter-session gap, unproven chart closure.
- Two additional diagnostic executions outside the earlier exception.
- `MONITOR_PROCEDURAL_COMPLIANCE=FAIL` remains unchanged.
- Existing raw journals and all earlier exception records remain immutable.

## Narrow clarification proposed

For a future Gate B permission-monitor preflight, the canonical criterion is:

| Criterion | Required value |
|---|---|
| monitor source | exact approved V2 source and matching EX5 SHA |
| attachment count | exactly one |
| chart | one newly owned temporary `BTCUSD,H1` |
| session | one session, no retry or extension |
| deadline | hard 600 monotonic seconds; stop request by 540 seconds |
| sampling | initial snapshot plus 60-second samples |
| gap | no within-session gap over 90 seconds |
| supervision | independent supervisor started before attachment |
| stop | controller bound to exact session/chart; no terminal-wide stop |
| cleanup | EA removal and owned-chart closure independently proven |
| safety | no diagnostic/V1, production EA, trade/login/credential/config change |

## Control-surface resolution

This proposal records capability evidence; it does not grant a control surface
and it does not approve a runtime. The current native Computer Use observation
was rechecked for this PR with `apps=[]` and browser surfaces only. An empty
native-app inventory is treated as no desktop authority, not as an implicit
MT5 capability.

| Capability | Evidence-backed status | Boundary |
|---|---|---|
| exact V2 source identity | `VERIFIED_OFFLINE` | Source SHA-256 `4984117c072662bf1ec55d187a04110cc06661eca687b041b5093081457b9ad6`; source review and Python harness only |
| compile exact V2 source | `NOT_PROVEN` | Observed shared MetaEditor build `5.0.0.6182` is only a candidate identity; no current V2 compile is promoted here |
| launch exact terminal process | `DOCUMENTED_PORTABLE_CONFIG_ONLY_NOT_AUTHORIZED` | `/portable` + `/config` + `[StartUp]` are prepared offline; no native launch surface or dedicated installation is authorized |
| launch `D:\Trading\MT5-V26` as a complete acceptance | `NOT_AVAILABLE` | The path/executable is recorded in existing preflight evidence, but no full launch-to-attach method is authorized or exercised by this proposal |
| create/own one `BTCUSD,H1` chart | `NOT_AVAILABLE` | Historical manual charts do not establish an automated, owned-chart adapter |
| attach once and bind chart/session | `NOT_AVAILABLE` | The offline adapter boundary is a fake/test boundary; no native chart ID/session controller exists |
| independent supervision | `VERIFIED_OFFLINE_DUMMY_ONLY` | Simulated monotonic clock and harmless dummy-process controller pass; no detached MT5 supervisor process was run |
| independent stop | `VERIFIED_OFFLINE_DUMMY_ONLY` | Exact controller/emergency authorization passes against dummy processes; live MT5 stop remains unavailable |
| removal and chart closure proof | `NOT_AVAILABLE` | No independent MT5 state observer or chart-close evidence is present |
| evidence collection/evaluation | `VERIFIED_OFFLINE_ONLY` | Bounded-copy/hash/parser/evaluator tests pass on temporary fixtures; no live evidence was collected |

The historical manual compile/attach observations therefore remain historical
evidence only. They do not prove that Codex can compile, launch, attach,
identify, stop or clean up a future session automatically.

## Architecture decision

### A. Existing shared terminal — rejected for unattended acceptance

`D:\Trading\MT5-V26` is a shared runtime with unrelated EA/chart state. The
current surface cannot bind a stop action to the exact terminal process,
chart ID, owner token and monitor session, nor can it prove chart closure.
Terminating the shared process would risk unrelated EAs. A journal-only
watchdog cannot repair this gap. Architecture A therefore does not satisfy
the contract and is not an implementation option for unattended acceptance.

### B. Dedicated isolated acceptance terminal — conditional, not proven

This is the only candidate architecture, but it is not available under the
current authority and has not been created or tested. It would require a
separate installation/data root, owned chart, one-shot supervisor process,
independent evidence root and an exact process identity. The operator would
perform any Investor login in the isolated terminal; credentials would not be
copied into the repository, controller configuration or evidence. The
controller would consume only the resulting non-secret account/server
identity and process/chart handles.

Before this can be called feasible, an authorized fixture must prove that the
controller can stop only the dedicated process/session and leave
`D:\Trading\MT5-V26` and its other EAs untouched. No second terminal, login or
process-stop test is authorized or performed by this amendment.

## Stop evidence is four separate facts

The contract must preserve these facts independently:

1. `SELF_STOP_REQUESTED` — the EA emitted its stop request (including an
   `ExpertRemove()` request). This is a request only.
2. `EA_REMOVAL_CONFIRMED` — an independent observer confirmed that the exact
   monitor instance is no longer attached to the exact chart, with deinit/
   removal evidence. It is not inferred from `ExpertRemove()`.
3. `CHART_CLOSURE_CONFIRMED` — an independent observer confirmed that the
   owned chart ID is closed. It is not inferred from a close request.
4. `INDEPENDENT_STOP_AVAILABLE` — a supervisor started before attachment can
   issue and verify a stop bound to the exact terminal/process, chart and
   session, without relying on the Codex session or a journal reader.

The offline harness covers the failure cases for missing independent stop,
chart-bound callback mismatch, rejected stop request, self-stop without
removal, missing chart-closure proof and cleanup crossing the 600-second
deadline. This proves fail-closed logic only. It does not prove a live
deadline, so `HARD_DEADLINE_PROVEN=NO` and unattended acceptance remains
forbidden.

## Required policy change (not approved here)

The current observability-only authority would have to be extended by two
narrow, separately recorded authorizations:

- **A1:** an operator-supplied verified provisioning source, isolated
  acceptance installation/data root, external evidence root, common-file
  no-write policy and dummy-process stop/rollback proof;
- **A2:** after A1 PASS, a native control adapter for one owned `BTCUSD,H1`
  chart and exact session/chart/process identity, with short bounded launch and
  stop proof; MQL5 compile/attach only if explicitly checked with the exact
  source/compiler/post-compile EX5-hash gate;
- a one-shot supervisor allowed to request and verify stop before 540 seconds
  and classify any unconfirmed cleanup at 600 seconds;
- process-stop authority scoped to the dedicated acceptance process only; and
- operator-performed Investor login only if a later record explicitly includes
  it, without copying credentials.

This is a policy prerequisite, not an approval to create a terminal, log in,
compile, attach, trade, enable Scheduler, start FORWARD or activate anything.

## Dedicated acceptance contract additions

These additions are part of the proposal only and become effective only after
the operator records the required amendment and execution approvals. They are
the minimum contract for the proposed isolated architecture:

| Area | Required contract | Current status |
|---|---|---|
| installation | dedicated installation root `D:\Trading\MT5-GateB-Acceptance`; never overwrite; never overlap `D:\Trading\MT5-V26` | proposed, not created |
| installer | `D:\mt5setup.exe`, SHA-256 `F15EEAE5E46DB7E94AFC2786C059266107E4AAED663B3318AFD4A3FC86D4F972`, Authenticode-valid MetaQuotes signer, version `5.0.0.5908` | local identity verified; provenance and file-specific path behavior pending |
| data root | dedicated portable data root, verified from runtime evidence | startup contract implemented; runtime not proven |
| common files | explicit collision-free `FILE_COMMON` root or acceptance-only namespace | not proven |
| source | `PR6_ReadOnlyPermissionMonitor_V2.mq5`, SHA-256 `4984117c072662bf1ec55d187a04110cc06661eca687b041b5093081457b9ad6` | verified offline |
| binary | exact EX5 produced from that source by the authorized compiler | not compiled; EX5 SHA unavailable |
| startup | `/portable` plus `/config`, `[StartUp] Expert/Symbol/Period`, live trading and DLL import denied | generated/validated offline only |
| launch | exact dedicated executable, data root, process creation identity and acceptance session | not authorized or executed |
| attachment | exactly one newly owned `BTCUSD,H1` chart; exact chart/session binding; no retry | native adapter unavailable |
| supervisor | separately running process started before launch; own monotonic clock; no Codex-session dependency | dummy-process proof only |
| stop | graceful request by 540 seconds; bounded emergency stop only for exact dedicated process; hard limit 600 seconds | mechanism implemented; MT5 proof absent |
| cleanup | independent `EA_REMOVAL_CONFIRMED`, `CHART_CLOSURE_CONFIRMED` and process-exit evidence | not run |
| evidence | new external root with source/EX5/config/process/chart/session hashes and immutable journals | collector/evaluator offline only |

The startup contract must be verified after an authorized launch because MT5
may fall back to defaults when a startup value is invalid. Runtime acceptance
must prove the actual data root, monitor loaded, one chart, `BTCUSD,H1`, the
expected account/server and no profile fallback. A startup process exit or
`ExpertRemove()` event alone is not sufficient.

The dedicated process supervisor must verify PID, executable path, creation
identity, Windows session, acceptance session and data root before both graceful
and emergency stop. Numeric-PID-only or terminal-wide termination is forbidden.
Dummy-process tests cover correct-target stop, wrong target, creation mismatch,
bounded timeout, emergency authorization and shared-V26 protection; those tests
are explicitly not real MT5 evidence.

The evaluator must keep `SELF_STOP_REQUESTED`, `EA_REMOVAL_CONFIRMED`,
`CHART_CLOSURE_CONFIRMED` and `INDEPENDENT_STOP_AVAILABLE` as separate facts.
Offline PASS, dummy-process PASS or a journal-only watchdog cannot set
`HARD_DEADLINE_PROVEN=YES`, `MONITOR_PREFLIGHT=PASS` or `GATE_B_OVERALL=PASS`.

## Approval A checkpoint split

The consolidated request now separates two operator decisions while retaining a
single approval document:

### A1 — isolated environment feasibility

A1 may authorize only the operator-supplied verified installation source,
dedicated root preparation, installation/data/common-file separation checks,
external evidence namespace, rollback record and harmless dummy-process stop
proof. A1 does not authorize MT5 launch, MetaEditor, MQL5 compile, V2 attach,
Investor login, trading or the 600-second Gate B session.

A1 PASS is blocked until the installation source and SHA, exact root policy,
portable data-root choice, `FILE_COMMON` no-write policy, evidence root and
rollback scope are explicit. The existing shared V26 installation remains
protected.

### A2 — MT5 control feasibility

A2 requires a recorded A1 PASS and a separate exact execution authorization.
It may launch only the named dedicated executable for a short bounded test,
verify actual process/data-root identity and startup behavior, optionally verify
one owned `BTCUSD,H1` chart, exercise exact independent stop and preserve
evidence. A2 is not full Monitor V2 acceptance.

MQL5 compile/load/attach is prohibited in A2 unless its exact source SHA,
compiler identity, post-compile EX5-hash approval gate, account/permission
scope, runtime limit and stop conditions are explicitly checked. A2 PASS does
not authorize Approval B.

The operator must make no implicit choice that emergency process termination
proves EA removal or chart closure. `PROCESS_TERMINATED` is a separate fact;
graceful cleanup requires independent `EA_REMOVAL_CONFIRMED` and
`CHART_CLOSURE_CONFIRMED`. No policy substitution is made by this proposal.

The prior 27 V1 samples may be cited only as
`MONITOR_FUNCTIONAL_EVIDENCE=PASS_FOR_OBSERVED_SAMPLES`. They may not be
promoted to continuous enforcement, procedural compliance or Monitor preflight
PASS. The two extra diagnostics remain an uncovered procedural incident.

## Approval boundaries

The following remain separate:

1. This contract/policy amendment approval.
2. A1 isolated-environment feasibility approval and evidence.
3. A2 short MT5 control-feasibility execution approval after A1 PASS.
4. Approval B for exact V2 source/EX5 plus one full monitor session after A2 PASS.
5. Production EX5/preset deployment and bounded real-telemetry approval.

No record may be generated or signed by the runner. Gate C Lite's policy
approval does not waive Gate B and does not create execution approval.

## Required decision

The operator must explicitly decide A1 in the single consolidated request. A2
may be decided only after A1 produces PASS evidence, and Approval B may be
decided only after A2 produces PASS evidence. Until then Gate B remains
blocked. Codex must not choose an exception merely because functional evidence
is consistent.
