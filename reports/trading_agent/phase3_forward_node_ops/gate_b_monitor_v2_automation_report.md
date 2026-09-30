# PR #6 Gate B Monitor V2 Automation Report

Status: `IMPLEMENTED_OFFLINE_APPROVAL_BOUNDARY`

## Scope and instruction boundary

The user request was to execute the attached PRD. The PRD itself limits this
turn to Stage 1 implementation, Stage 2 offline validation and Stage 3
approval preparation. Its Stage 4/5 actions require separate operator records,
and its hard stops prohibit creating or launching a second terminal, logging
in, compiling/attaching MT5, production EA changes, trading, Scheduler,
FORWARD, Gate C, merge and activation. Those runtime actions were not taken.

The existing shared terminal `D:\Trading\MT5-V26` was not touched. The
proposed dedicated root `D:\Trading\MT5-GateB-Acceptance` was not created.
No credentials were read or copied.

## Implemented components

```text
agent/phase3/gate_b_monitor/PR6_ReadOnlyPermissionMonitor_V2.mq5
agent/phase3/gate_b_monitor/orchestrator.py
agent/phase3/gate_b_monitor/supervisor.py
agent/phase3/gate_b_monitor/collector.py
agent/phase3/gate_b_monitor/evaluator.py
agent/phase3/gate_b_monitor/models.py
agent/phase3/gate_b_monitor/provisioning.py
agent/phase3/gate_b_monitor/startup.py
agent/phase3/gate_b_monitor/compiler.py
agent/phase3/gate_b_monitor/controller.py
agent/phase3/gate_b_monitor/process_supervisor.py
agent/phase3/gate_b_monitor/__init__.py
agent/tests/test_gate_b_monitor_automation.py
agent/tests/test_gate_b_dedicated_components.py
docs/trading_agent/phase3/GATE_B_MONITOR_V2_RUNBOOK.md
docs/trading_agent/phase3/GATE_B_MONITOR_V2_CONTRACT_AMENDMENT.md
outputs/gate_b_msi_monitor_v2_automation_20260921T084200Z/operator-approval-request.md
outputs/gate_b_msi_monitor_v2_automation_20260921T084200Z/offline-full-prd-validation.json
```

The provisioner is read-only by default and rejects an existing/overlapping
target, shared V26 paths, common-root collisions and unsafe evidence roots.
Empty-layout creation is separately authorization-gated and was not invoked.
The startup generator is credential-free and emits the documented `/portable`
and `/config` contract for one `BTCUSD,H1` monitor chart. The compiler plans
the exact MetaEditor command and validates compiler output but refuses to run
without the separate execution approval.

The process controller verifies PID, executable path, creation token, Windows
session, acceptance session and data root before stop. The independent runner
owns its own monotonic clock, requests stop by 540 seconds, and enforces the
600-second boundary for the exact authorized process. Emergency termination is
authorization-gated. It is not a terminal-wide kill and never targets V26.

The offline evaluator includes all mandatory dedicated-acceptance fields and
keeps `SELF_STOP_REQUESTED`, `EA_REMOVAL_CONFIRMED`,
`CHART_CLOSURE_CONFIRMED` and `INDEPENDENT_STOP_AVAILABLE` separate. It never
promotes offline or dummy-process PASS to real `MONITOR_PREFLIGHT` or Gate B.

## Verification

```text
python -m compileall -q agent                         PASS
python -m unittest discover -s agent/tests             128/128 PASS
python -m unittest agent.tests.test_gate_b_dedicated_components  16/16 PASS
python -m unittest agent.tests.test_gate_b_monitor_automation    16/16 PASS
python -m unittest agent.tests.test_mt5_watchdog                  10/10 PASS
git diff --check                                      PASS
PowerShell parse checks                               NOT_APPLICABLE (no new PS script)
MQL5 compile                                          NOT_RUN
MT5 launch/attach                                     NOT_RUN
```

The dedicated tests include wrong target/path, data-root/common-root guards,
startup fallback/tamper/credential guards, compile failure/hash guards,
session/attach blocking, exact process identity, wrong creation identity, PID
reuse protection, graceful timeout, authorization-gated emergency stop,
supervisor soft/hard deadlines, shared V26 protection and evaluator fail-closed
cases. They use only temporary files and harmless dummy processes. Dummy
process PASS does not prove MT5 process stop.

The startup and compile design follows the documented MT5 `/portable`,
`/config`, `[StartUp]` and MetaEditor compilation interfaces; actual behavior
must still be verified against the installed version in an authorized fixture:

- https://www.metatrader5.com/en/terminal/help/start_advanced/start
- https://www.metatrader5.com/en/metaeditor/help/development/compile
- https://www.metatrader5.com/en/metaeditor/help/beginning/integration_ide

## Architecture result

| Architecture | Result | Reason |
|---|---|---|
| Existing shared terminal `D:\Trading\MT5-V26` | `REJECTED` | no proven exact chart/session/process stop; terminal-wide stop could affect unrelated EAs |
| Dedicated isolated terminal | `CONDITIONAL_NOT_PROVEN` | implementation and dummy proof exist, but no authorized installation, runtime isolation, native chart adapter, login, MT5 compile/attach or live stop proof |

Current native CUA state was `apps=[]`; this is no desktop authority. The
documented startup command and offline controller are therefore not a
supported live launch/attach surface in this turn.

## Required result fields

```text
IMPLEMENTATION_STATUS=STAGE_1_2_3_COMPLETE; OFFLINE_ONLY; APPROVAL_BOUNDARY
FILES_CHANGED=provisioning.py; startup.py; compiler.py; controller.py; process_supervisor.py; evaluator.py; __init__.py; Gate B tests; runbook; amendment; consolidated request; report; evidence
CODE_BRANCH_AND_SHA=codex/mt5-v26-v63-recovery-watchdog @ 321cdeed361a3e9cb650647ee6fc386d4cf10cd3 (uncommitted workspace changes)
APPROVED_PRODUCTION_SHA_UNCHANGED=YES; bbf87b40eb72de35318608cb9e4d4f77d150e32a
DEDICATED_TERMINAL_ROOT=D:\Trading\MT5-GateB-Acceptance; NOT_CREATED
PROVISIONER_STATUS=IMPLEMENTED_READ_ONLY_PREFLIGHT; CREATION_APPROVAL_GATED_NOT_RUN
PORTABLE_MODE_SUPPORT=IMPLEMENTED_STARTUP_CONTRACT; RUNTIME_UNVERIFIED
DATA_ROOT_ISOLATION=NOT_PROVEN
FILE_COMMON_ISOLATION=NOT_PROVEN; ACCEPTANCE_NAMESPACE_REQUIRED
STARTUP_CONFIG_IMPLEMENTED=YES_OFFLINE_CREDENTIAL_FREE
AUTOMATED_LAUNCH_METHOD=DOCUMENTED terminal64.exe /portable /config:<config>; OFFLINE_ONLY_NOT_AUTHORIZED
AUTOMATED_ATTACH_METHOD=NONE; NATIVE_MT5_CONTROL_SURFACE_UNAVAILABLE
EXACT_CHART_BINDING=OFFLINE_CONTRACT_REQUIRES_SESSION_ID_AND_CHART_ID; LIVE_NOT_PROVEN
MONITOR_V2_SOURCE_SHA=4984117c072662bf1ec55d187a04110cc06661eca687b041b5093081457b9ad6
MONITOR_V2_EX5_SHA=NOT_AVAILABLE_NOT_COMPILED
MONITOR_V2_COMPILE=PLAN_IMPLEMENTED; NOT_RUN
SUPERVISOR_STATUS=IMPLEMENTED_INDEPENDENT_RUNNER; OFFLINE_ONLY
PROCESS_OWNERSHIP_VERIFICATION=EXACT_PID_PATH_CREATION_WINDOWS_SESSION_ACCEPTANCE_SESSION_DATA_ROOT; DUMMY_PROVEN
INDEPENDENT_STOP_IMPLEMENTED=YES; EXACT_PROCESS_CONTROLLER; EMERGENCY_AUTHORIZATION_GATE
INDEPENDENT_STOP_PROVEN=DUMMY_PROCESS_ONLY; LIVE_MT5_NO
HARD_DEADLINE_PROVEN=NO_FOR_REAL_MT5
GUI_AUTOMATION_REQUIRED=YES_WITH_CURRENT_APPS_EMPTY
MANUAL_ACTIONS_REMAINING=A1 verified installer/source and root decisions; then separate A2 short control authorization; optional MQL5 hash gate; then Approval B
STATIC_TESTS=compileall PASS; git diff --check PASS; no new PowerShell script
UNIT_TESTS=128/128 PASS
INTEGRATION_TESTS=OFFLINE_CONTROLLER_AND_EVALUATOR_PASS; REAL_MT5_NOT_RUN
DUMMY_PROCESS_TESTS=PASS; exact-target graceful timeout/emergency and deadline cases
REAL_MT5_FEASIBILITY=CONDITIONAL_NOT_PROVEN
REAL_MONITOR_ACCEPTANCE=NOT_RUN
CONTRACT_AMENDMENT_STATUS=UPDATED_PROPOSAL_NOT_APPROVED
OPERATOR_APPROVAL_REQUIRED=YES; consolidated A1/A2 request, then separate Approval B
APPROVAL_REQUEST_PATH=D:\Trading\buildbot\outputs\gate_b_msi_monitor_v2_automation_20260921T084200Z\operator-approval-request.md
REPORT_PATH=D:\Trading\buildbot\reports\trading_agent\phase3_forward_node_ops\gate_b_monitor_v2_automation_report.md
EVIDENCE_PATH=D:\Trading\buildbot\outputs\gate_b_msi_monitor_v2_automation_20260921T084200Z\offline-full-prd-validation.json
EXACT_NEXT_ACTION=Operator accepts or rejects D:\mt5setup.exe hash/signature/provenance/path method and records A1 decision; A2 remains gated on A1 PASS
MONITOR_PREFLIGHT=BLOCKED; REAL_SESSION_NOT_RUN
REAL_TELEMETRY=NOT_RUN
GATE_B_OVERALL=BLOCKED
MERGE_READY=NO
ACTIVATION_READY=NO
```

The prior V1 procedural `FAIL`, historical journals and old exception evidence
remain unchanged. No amendment was self-approved and no runtime action is
implied by this report.

## Approval A finalization result

The finalization PRD was applied as a documentation/read-only reconciliation;
Stage 1–3 implementation and the completed offline suite were not restarted.
The host checks found the existing V26 terminal and MetaEditor identities, the
shared data root and shared `FILE_COMMON` directory, plus the exact local
installer `D:\mt5setup.exe` (SHA-256
`F15EEAE5E46DB7E94AFC2786C059266107E4AAED663B3318AFD4A3FC86D4F972`, valid
MetaQuotes Authenticode signature, version `5.0.0.5908`). Official MT5
documentation describes `/auto /path`, but this file was not executed, so
file-specific install behavior and download provenance remain pending. No
dedicated root, startup INI or real V2 EX5 exists.

Installer reference: https://www.metatrader5.com/en/terminal/help/start_advanced/installation

```text
APPROVAL_A1_READY=YES_REVIEWABLE_NOT_APPROVED
APPROVAL_A2_READY=YES_SCOPED_AND_DEPENDENT_ON_A1_PASS; NOT_EXECUTABLE_NOW
FIXTURE_COMPLETENESS=COMPLETE_FOR_READ_ONLY_DOSSIER; INSTALLER_PROVENANCE_AND_RUNTIME_VALUES_PENDING
CONTRACT_CONSISTENCY=PASS_PROPOSAL_CONSISTENT_WITH_A1_A2_AND_IMPLEMENTATION
REQUIRED_OPERATOR_DECISIONS=A1_INSTALLER_HASH_SIGNATURE_PROVENANCE_PATH_METHOD_AND_ROOT_POLICY; A2_SHORT_CONTROL_TEST; OPTIONAL_A2_MQL5_HASH_GATE
EXACT_ACTIONS_AFTER_APPROVAL=PROVISION_AND_PROVE_A1; THEN SEPARATELY_AUTHORIZE_SHORT_A2; THEN REQUEST_APPROVAL_B
REPORT_PATH=D:\Trading\buildbot\reports\trading_agent\phase3_forward_node_ops\gate_b_monitor_v2_automation_report.md
UPDATED_APPROVAL_REQUEST_PATH=D:\Trading\buildbot\outputs\gate_b_msi_monitor_v2_automation_20260921T084200Z\operator-approval-request.md
CONTRACT_AMENDMENT_PATH=D:\Trading\buildbot\docs\trading_agent\phase3\GATE_B_MONITOR_V2_CONTRACT_AMENDMENT.md
EXACT_NEXT_ACTION=OPERATOR_ACCEPTS_OR_REJECTS_D:\mt5setup.exe_HASH_SIGNATURE_PROVENANCE_AND_PATH_METHOD_THEN_RECORDS_A1_DECISION

REAL_MT5_FEASIBILITY=NOT_RUN
REAL_MONITOR_ACCEPTANCE=NOT_RUN
GATE_B_OVERALL=BLOCKED
MERGE_READY=NO
ACTIVATION_READY=NO
```
