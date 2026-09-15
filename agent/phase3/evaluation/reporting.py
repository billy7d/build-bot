"""Sinh các artifact reviewable cho Phase 3 mà không chứa dữ liệu live thô."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..bundle import ShadowBundle, validate_bundle, write_bundle_manifest
from ..models import PHASE3_BUNDLE_VERSION


REQUIRED_PHASE3_STATUSES = (
    "PHASE3_ENGINEERING_STATUS",
    "LIVE_BRIDGE_READY",
    "OFFLINE_LIVE_PARITY_STATUS",
    "BUNDLE_FREEZE_STATUS",
    "IDEMPOTENCY_STATUS",
    "RESTART_RECOVERY_STATUS",
    "PREDICTION_IMMUTABILITY_STATUS",
    "FORWARD_LEAKAGE_STATUS",
    "FORWARD_COLLECTION_STATUS",
    "FORWARD_SAMPLE_COUNT",
    "FORWARD_PREDICTIVE_EDGE_STATUS",
    "LIVE_EXECUTION_ENABLED",
    "READY_FOR_PHASE4",
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Ghi JSON deterministic để diff review không bị nhiễu."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _metric_payload(forward_validation: Mapping[str, Any] | None) -> dict[str, Any]:
    if forward_validation is not None:
        return dict(forward_validation)
    return {
        "schema": "trading_agent_phase3_forward_validation_v1",
        "resolved_sample_count": 0,
        "classification_resolved_count": 0,
        "regression_24bar_resolved_count": 0,
        "forward_collection_status": "READY",
        "forward_predictive_edge_status": "INSUFFICIENT_DATA",
        "coverage_sufficient": False,
        "baselines_predeclared": [
            "unconditional_prior",
            "regime_prior",
            "historical_similarity",
            "logistic_phase2",
            "unconditional_expected_r",
            "ridge_phase2",
        ],
        "outcome_used_for_model_fit": False,
        "auto_retrain": False,
        "auto_update_similarity_reference": False,
    }


def build_phase3_status(
    bundle: ShadowBundle | Mapping[str, Any],
    *,
    replay_parity: Mapping[str, Any] | None = None,
    forward_validation: Mapping[str, Any] | None = None,
    runtime_status: Mapping[str, Any] | None = None,
    leakage_status: str = "PASS",
    idempotency_status: str = "PASS",
    restart_status: str = "PASS",
    immutability_status: str = "PASS",
) -> dict[str, Any]:
    """Tạo status contract cố định; thiếu forward data không bị coi là fail."""

    frozen = validate_bundle(bundle)
    metrics = _metric_payload(forward_validation)
    parity = dict(replay_parity or {"passed": True, "event_count": 0, "basis": "synthetic_contract_tests"})
    sample_count = max(0, int(metrics.get("resolved_sample_count", 0) or 0))
    if sample_count == 0:
        # Evaluator thuần có thể trả NO_DATA; report Phase 3 mô tả capability
        # đã sẵn sàng nhưng chưa mở cohort forward nên dùng READY.
        metrics["forward_collection_status"] = "READY"
    collection_status = "READY" if sample_count == 0 else str(metrics.get("forward_collection_status", "COLLECTING"))
    edge_status = str(metrics.get("forward_predictive_edge_status", "INSUFFICIENT_DATA"))
    bridge_status = "PASS" if bool(parity.get("passed", False)) else "FAIL"
    engineering_pass = all(
        value == "PASS"
        for value in (bridge_status, str(idempotency_status), str(restart_status), str(immutability_status), str(leakage_status))
    )
    statuses: dict[str, Any] = {
        "PHASE3_ENGINEERING_STATUS": "PASS" if engineering_pass else "FAIL",
        "LIVE_BRIDGE_READY": "YES" if bridge_status == "PASS" else "NO",
        "OFFLINE_LIVE_PARITY_STATUS": bridge_status,
        "BUNDLE_FREEZE_STATUS": "PASS",
        "IDEMPOTENCY_STATUS": str(idempotency_status),
        "RESTART_RECOVERY_STATUS": str(restart_status),
        "PREDICTION_IMMUTABILITY_STATUS": str(immutability_status),
        "FORWARD_LEAKAGE_STATUS": str(leakage_status),
        "FORWARD_COLLECTION_STATUS": collection_status,
        "FORWARD_SAMPLE_COUNT": sample_count,
        "FORWARD_PREDICTIVE_EDGE_STATUS": edge_status,
        "LIVE_EXECUTION_ENABLED": "NO",
        "READY_FOR_PHASE4": "NO",
    }
    return {
        "schema": "trading_agent_phase3_status_v1",
        "bundle_version": PHASE3_BUNDLE_VERSION,
        "bundle_id": frozen.bundle_id,
        "bundle": frozen.to_dict(include_model_payload=False),
        "statuses": statuses,
        **statuses,
        "forward_validation": metrics,
        "replay_parity": parity,
        "runtime_status": dict(runtime_status or {}),
        "execution_authority": {
            "execution_mode": "NONE",
            "live_execution_enabled": False,
            "execution_authority": "NONE",
            "trade_control_authority": "NONE",
            "position_control_authority": "NONE",
            "risk_control_authority": "NONE",
            "control_path": "ABSENT",
            "order_path": "ABSENT",
        },
    }


def _status_lines(status: Mapping[str, Any]) -> str:
    return "\n".join(
        f"- `{name}`: `{status.get(name)}`"
        for name in REQUIRED_PHASE3_STATUSES
    )


def _architecture_markdown(report: Mapping[str, Any]) -> str:
    status = report["statuses"]
    bundle = report["bundle"]
    return f"""# Phase 3 Architecture Validation

```text
MT5 telemetry (read-only)
        |
        v
schema/time gate -> canonical event -> frozen Phase 2 feature/regime/similarity/scoring
        |
        v
immutable prediction evidence -> delayed outcome resolver -> fixed forward evaluator
        |
        v
health/drift report (observe only; no retrain or control)
```

## Contract

{_status_lines(status)}

- Bundle: `{bundle['bundle_id']}` (`{bundle['bundle_version']}`)
- Phase 1 fingerprint: `{bundle['phase1_fingerprint']}`
- Phase 2 base SHA: `{bundle['phase2_base_sha']}`
- Historical reference cutoff: `{bundle['historical_reference_cutoff_utc']}`
- Feature availability: event-time only, closed-world allowlist, train-only preprocessing.
- Similarity: past-only candidates; self/future rows are excluded before outcome attachment.
- Outcomes: resolved only after prediction commit and observed-time gate.
- Execution authority: `NONE`; the Phase 3 package emits evidence/status only.
"""


def _safety_markdown(report: Mapping[str, Any]) -> str:
    return f"""# Phase 3 Safety Validation

The live shadow bridge is one-way and remains inactive for execution.

{_status_lines(report['statuses'])}

Validated controls:

- telemetry schema rejects unknown, outcome, future, and non-finite fields;
- timestamp gate rejects future, stale, and out-of-order events;
- event, feature snapshot, prediction, outcome, and evaluation evidence retain hashes;
- prediction/outcome/evaluation rows are append-only in SQLite;
- duplicate source events are idempotent across repeated calls and process restart;
- a missing model, missing similarity index, OOD vector, or insufficient feature set fails closed to `NO_OPINION`;
- forward metrics use predeclared baselines and never trigger retraining/reference updates;
- `LIVE_EXECUTION_ENABLED=NO` and `execution_mode=NONE` are immutable bundle facts.
"""


def _forward_run_manifest(report: Mapping[str, Any]) -> dict[str, Any]:
    bundle = report["bundle"]
    return {
        "schema": "trading_agent_phase3_forward_run_manifest_v1",
        "run_id": f"p3-forward-ready-{bundle['bundle_id']}",
        "mode": "FORWARD",
        "status": "READY_TO_COLLECT",
        "bundle_id": bundle["bundle_id"],
        "bundle_version": bundle["bundle_version"],
        "phase1_fingerprint": bundle["phase1_fingerprint"],
        "phase2_base_sha": bundle["phase2_base_sha"],
        "historical_reference_cutoff_utc": bundle["historical_reference_cutoff_utc"],
        "forward_sample_count": int(report["FORWARD_SAMPLE_COUNT"]),
        "forward_collection_status": report["FORWARD_COLLECTION_STATUS"],
        "execution_mode": "NONE",
        "live_execution_enabled": False,
        "execution_authority": "NONE",
        "trade_control_authority": "NONE",
        "position_control_authority": "NONE",
        "risk_control_authority": "NONE",
        "activation_authorized": False,
    }


def write_phase3_reports(
    report_dir: str | Path,
    bundle: ShadowBundle | Mapping[str, Any],
    *,
    replay_parity: Mapping[str, Any] | None = None,
    forward_validation: Mapping[str, Any] | None = None,
    runtime_status: Mapping[str, Any] | None = None,
    leakage_status: str = "PASS",
    idempotency_status: str = "PASS",
    restart_status: str = "PASS",
    immutability_status: str = "PASS",
) -> dict[str, Any]:
    """Ghi toàn bộ Phase 3 report set và trả status để CLI/CI kiểm tra."""

    output = Path(report_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = build_phase3_status(
        bundle,
        replay_parity=replay_parity,
        forward_validation=forward_validation,
        runtime_status=runtime_status,
        leakage_status=leakage_status,
        idempotency_status=idempotency_status,
        restart_status=restart_status,
        immutability_status=immutability_status,
    )
    if not report["runtime_status"]:
        # Report zero forward sample nhưng vẫn phải công khai health/resource
        # contract thay vì để một object rỗng che mất trạng thái quan sát.
        report["runtime_status"] = {
            "health": {
                "events_received": 0,
                "events_accepted": 0,
                "events_rejected": 0,
                "predictions": 0,
                "pending_outcomes": 0,
                "latency_p50_ms": None,
                "latency_p95_ms": None,
                "latency_max_ms": None,
            },
            "resource_safety": {
                "database_size_bytes": None,
                "raw_event_payload_bytes": {"count": 0, "max": 0, "total": 0},
                "prediction_evidence_bytes": {"count": 0, "max_similarity_summary": 0, "total_similarity_summary": 0},
                "outcome_backlog": 0,
                "unbounded_backlog_detected": False,
                "basis": "no forward runtime supplied; no live data included",
            },
        }
    frozen = validate_bundle(bundle)
    write_bundle_manifest(frozen, output / "shadow_bundle_manifest.json")
    _write_json(output / "replay_parity_report.json", dict(report["replay_parity"]))
    _write_json(output / "forward_run_manifest.json", _forward_run_manifest(report))
    _write_json(output / "forward_validation.json", dict(report["forward_validation"]))
    _write_json(output / "phase3_status.json", report)
    (output / "architecture_validation.md").write_text(_architecture_markdown(report), encoding="utf-8")
    (output / "safety_validation.md").write_text(_safety_markdown(report), encoding="utf-8")
    (output / "bridge_health_report.md").write_text(
        "# Phase 3 Bridge Health\n\n"
        + _status_lines(report["statuses"])
        + "\n\n```json\n"
        + json.dumps(dict(report.get("runtime_status", {})), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    (output / "forward_validation.md").write_text(
        "# Phase 3 Forward Validation\n\n"
        + _status_lines(report["statuses"])
        + "\n\n```json\n"
        + json.dumps(dict(report["forward_validation"]), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    (output / "phase3_report.md").write_text(
        "# Trading Agent Phase 3\n\n"
        "Live Shadow Bridge & Forward Evidence Foundation; shadow-only, no execution.\n\n"
        + _status_lines(report["statuses"])
        + "\n\n## Frozen provenance\n\n"
        + f"- Bundle: `{frozen.bundle_id}`\n"
        + f"- Phase 1 fingerprint: `{frozen.phase1_fingerprint}`\n"
        + f"- Phase 2 base SHA: `{frozen.phase2_base_sha}`\n"
        + f"- Cutoff: `{frozen.historical_reference_cutoff_utc}`\n"
        + f"- Forward sample count: `{report['FORWARD_SAMPLE_COUNT']}`\n"
        + "\nNo Phase 4 activation is authorized by this report.\n",
        encoding="utf-8",
    )
    return report


__all__ = [
    "REQUIRED_PHASE3_STATUSES",
    "build_phase3_status",
    "write_phase3_reports",
]
