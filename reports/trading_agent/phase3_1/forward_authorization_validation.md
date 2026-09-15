# Forward authorization validation

## Contract

The local manifest schema is `phase3-forward-authorization/1`. Authorization
is bound to the exact current Git SHA, frozen bundle/model/index fingerprints,
telemetry source identity, runtime DB, and all required safety gates:

```text
execution_mode = NONE
live_execution_enabled = false
execution_api_path_count = 0
replay_parity_status = PASS
smoke_status = PASS
db_integrity_status = PASS
one_way_safety_status = PASS
```

`prepare-forward` never starts a collector. `start-forward` validates the
manifest and current source identity before creating a new run. `resume-forward`
uses the stored run and rejects a stopped or failed run, a mismatched SHA, and
an active source owned by another run.

## Test evidence

The Phase 3.1 tests passed valid manifest/hash/assets validation, missing
authorization rejection, tampered hash rejection, frozen model/index gates,
and the zero execution scan. Existing untracked local data was not considered
a tracked worktree change.

No real authorization manifest was written because the required MT5 telemetry
source was unavailable. Consequently there is no authorized Git SHA, forward
run ID, source offset, or `ACTIVE` status to report.

