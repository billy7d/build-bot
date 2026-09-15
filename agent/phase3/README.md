# Trading Agent Phase 3

Phase 3 is a one-way, shadow-only bridge from recorded telemetry to the frozen Phase 2 intelligence contract. It stores evidence and delayed outcomes; it has no execution authority.

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
```

`freeze-bundle` reads the Phase 1/Phase 2 manifests and the local ignored Phase 2 model artifact when present. The reviewable manifest contains fingerprints and train-only preprocessing metadata, not the model payload. A model artifact and optional historical index can be supplied to replay/start-shadow through `--model-bundle` and `--history-json`.

The telemetry contract is `phase3-live-telemetry/1`: closed-bar event-time features only, UTC timestamps, deterministic source IDs, and no outcome/future fields. Repeated source IDs are idempotent. File ingestion advances only across complete lines and detects rotation.

Forward outcomes are resolved only from bars strictly after both the event timestamp and prediction commit timestamp. Fixed metrics use predeclared baselines, deterministic block bootstrap, and never retrain or update the similarity reference.

The Phase 3 default is `execution_mode=NONE`, `LIVE_EXECUTION_ENABLED=NO`. The `start-shadow` CLI intentionally refuses `FORWARD`; forward collection remains a separately reviewable, non-executing authorization step.
