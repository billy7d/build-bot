# Trading Agent Phase 3

Phase 3 is a one-way, shadow-only bridge from recorded telemetry to the frozen Phase 2 intelligence contract. It stores evidence and delayed outcomes; it has no execution authority. Phase 3.1 adds a persistent Windows collector, but the execution contract remains `execution_mode=NONE` and `LIVE_EXECUTION_ENABLED=NO`.

## Commands

From the repository root:

```text
python -m agent.phase3 freeze-bundle
python -m agent.phase3 validate-bundle
python -m agent.phase3 start-shadow --run-id p3-smoke-1
python -m agent.phase3 replay --telemetry path/to/telemetry.jsonl --run-id p3-replay-1
python -m agent.phase3 status --run-id p3-smoke-1
python -m agent.phase3 resolve-outcomes --run-id p3-forward-1 --outcomes path/to/outcomes.json
python -m agent.phase3 evaluate --run-id p3-forward-1
python -m agent.phase3 report
python -m agent.phase3 build-history-index --source-db <phase1.sqlite> --output <runtime-index.json>
python -m agent.phase3 prepare-forward --runtime-config E:\build-bot-runtime\phase3\config\forward.json --gates <gate-evidence.json>
python -m agent.phase3 start-forward --runtime-config E:\build-bot-runtime\phase3\config\forward.json
python -m agent.phase3 resume-forward --runtime-config E:\build-bot-runtime\phase3\config\forward.json --run-id <run-id>
python -m agent.phase3 stop-forward --runtime-config E:\build-bot-runtime\phase3\config\forward.json --run-id <run-id>
python -m agent.phase3 status-runtime --runtime-config E:\build-bot-runtime\phase3\config\forward.json --json
```

`freeze-bundle` reads the Phase 1/Phase 2 manifests and the local ignored Phase 2 model artifact when present. The reviewable manifest contains fingerprints and train-only preprocessing metadata, not the model payload. A model artifact and optional historical index can be supplied to replay/start-shadow through `--model-bundle` and `--history-json`.

The telemetry contract is `phase3-live-telemetry/1`: closed-bar event-time features only, UTC timestamps, deterministic source IDs, and no outcome/future fields. Repeated source IDs are idempotent. File ingestion advances only across complete lines and detects rotation.

Forward outcomes are resolved only from bars strictly after both the event timestamp and prediction commit timestamp. Fixed metrics use predeclared baselines, deterministic block bootstrap, and never retrain or update the similarity reference.

The Phase 3 default is `execution_mode=NONE`, `LIVE_EXECUTION_ENABLED=NO`. The `start-shadow` CLI intentionally refuses `FORWARD`; forward collection remains a separately reviewable, non-executing authorization step.

## Phase 3.1 runtime

The runtime configuration and mutable state live outside the repository, normally under:

```text
E:\build-bot-runtime\phase3\
  config\forward.json
  config\forward_authorization.json
  telemetry\
  db\phase3-forward.sqlite
  logs\
  state\heartbeat.json
  state\collector.lock
  state\current_run.json
```

The collector binds the first observed source identity to the current end-of-file offset. It then resumes the persisted offset on restart, allows a genuine file rotation, and fails the run closed on same-identity truncation. A stale lock file does not block recovery because the collector uses an operating-system file lock held for the process lifetime.

Windows Task Scheduler helpers are in `scripts\phase3\`:

```powershell
.\scripts\phase3\install_forward_task.ps1
.\scripts\phase3\start_forward_task.ps1
.\scripts\phase3\status_forward_task.ps1
.\scripts\phase3\stop_forward_task.ps1
.\scripts\phase3\uninstall_forward_task.ps1
```

Installation is disabled/stopped by default. The task is named `BuildBot-Phase3-Forward`, runs as the interactive user without a stored password, ignores concurrent instances, has no execution time limit, and is scoped to the collector process only. `run_forward_collector.ps1` resumes the persisted run marker after a restart; passing `-NewRun` intentionally starts a new authorized run.

The MT5 side-channel writes one complete `phase3-live-telemetry/1` JSONL record to `FILE_COMMON` at:

```text
<MT5 common data path>\Files\phase3\Mentor_RSI_MTF_<MagicNumber>_<Symbol>_<Timeframe>.jsonl
```

The exporter is `void` and is called after the existing trade request returns; its file/open/write result is not used to gate entry, exit, risk, lot, SL, or TP behavior. Existing account/execution CSV telemetry is not the opportunity schema and is therefore not reused as the Phase 3 source.

No authorization manifest is created unless the exact current Git SHA, frozen bundle/model/index, replay/smoke/database/one-way gates, and real telemetry source identity all pass. Synthetic or historical records never prove `MT5_TELEMETRY_STATUS=CONNECTED` or `FORWARD_COLLECTION_STATUS=ACTIVE`.
