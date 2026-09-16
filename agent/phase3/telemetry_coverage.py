"""Đo coverage canonical từ nguồn audit Phase 1 mà không đọc outcome vào payload."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..data.episodes.builder import (
    V81_EVENT_TIME_FEATURE_FIELDS,
    V81_FEATURE_SOURCE_MAP,
    V82_EVENT_TIME_FEATURE_FIELDS,
    V82_FEATURE_SOURCE_MAP,
)
from ..data.models import NormalizedEvent
from ..data.normalization.canonical import canonical_opportunity_id
from ..data.parsers import v81_stddev, v82_blocked_signal
from .ingestion.opportunity import (
    CANONICALIZER_FINGERPRINT,
    canonicalize_observation,
    validate_opportunity_payload,
)


PHASE1_DATASET_FINGERPRINT = "2dc6dcd74928ed00923fd21f032ba0700f1c9c50459c9e0159872aa2045680ff"


def discover_historical_audit_sources(repo_root: str | Path) -> tuple[Path, ...]:
    """Tìm đúng raw V81/V82 đã được inventory, không tạo hoặc sửa dữ liệu."""

    root = Path(repo_root)
    paths = list(root.glob("outputs/build/v81-runs/*/shadow-signals.csv"))
    paths.extend(root.glob("outputs/build/v82_runs/*_blocked_signals.csv"))
    return tuple(sorted(path for path in paths if path.is_file()))


def _event_type(event: NormalizedEvent) -> str:
    return str(event.fields.get("raw_event_type") or event.event_type).upper()


def _safe_features(event: NormalizedEvent) -> dict[str, Any]:
    """Chỉ chuyển field event-time sang tên feature đã đăng ký."""

    mapping = V81_FEATURE_SOURCE_MAP if event.audit_version == "V81" else V82_FEATURE_SOURCE_MAP
    names = V81_EVENT_TIME_FEATURE_FIELDS if event.audit_version == "V81" else V82_EVENT_TIME_FEATURE_FIELDS
    features: dict[str, Any] = {}
    for target, source in mapping.items():
        value = event.fields.get(source)
        if value is not None:
            features[target] = value
    for source in names:
        value = event.fields.get(source)
        if value is None:
            continue
        target = {
            "entry_atr_pct": "atr_percent",
            "entry_spread_r": "spread_r",
        }.get(source, source)
        if target in {
            "rsi", "atr_percent", "spread_r", "entry_atr_rank", "entry_efficiency_20",
            "initial_sl_atr", "d1_regime_score", "h4_regime_score", "composite_regime_score",
        }:
            features[target] = value
    features.update(
        {
            "symbol": event.symbol,
            "timeframe": event.timeframe,
            "side": event.side,
            "strategy_version": event.strategy_version or "UNKNOWN",
        }
    )
    return features


def observation_payload_from_normalized(event: NormalizedEvent) -> dict[str, Any]:
    """Tạo raw observation replay mà không sao chép các outcome fields."""

    fields = event.fields
    risk = fields.get("risk_distance", fields.get("shadow_risk_distance"))
    stop = fields.get("initial_sl", fields.get("shadow_initial_sl"))
    build_valid = event.price is not None and risk is not None and stop is not None
    payload: dict[str, Any] = {
        "schema_version": "phase3-opportunity-observation/1",
        "source_observation_id": f"{event.audit_version}:{event.raw_event_id}",
        "event_timestamp_utc": event.event_time_utc,
        "emitted_at_utc": event.event_time_utc,
        "source_strategy": "Mentor_RSI_MTF",
        "source_strategy_version": event.strategy_version or "UNKNOWN",
        "symbol": event.symbol,
        "timeframe": event.timeframe,
        "side": event.side,
        "source_audit_family": event.audit_version or "UNKNOWN",
        "source_event_type": _event_type(event),
        "bar_state": "closed_bar",
        "context": {"features": _safe_features(event)},
        "execution_context": {
            "audit_family": event.audit_version or "UNKNOWN",
            "blocked_reason": _event_type(event),
            "execution_eligible": False,
        },
        "entry_price": event.price,
        "hypothetical_entry_price": event.price,
        "risk_distance": risk,
        "initial_sl_distance": risk,
        "hypothetical_initial_sl": stop,
        "build_valid": build_valid,
    }
    if not build_valid:
        payload["build_reason"] = "MISSING_HYPOTHETICAL_BUILD_FIELDS"
    return payload


def _load_events(paths: Iterable[Path]) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    for path in paths:
        if "v82" in path.as_posix().lower():
            events.extend(v82_blocked_signal.parse(path, source_key=str(path), source_timezone="UTC"))
        else:
            events.extend(v81_stddev.parse(path, source_key=str(path), source_timezone="UTC"))
    return events


def _month(timestamp: str) -> str:
    value = str(timestamp).replace("Z", "+00:00")
    return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y-%m")


def _phase1_db_metrics(path: str | Path, canonical_ids: set[str]) -> dict[str, Any]:
    source = Path(path).resolve()
    if not source.is_file():
        return {"scorable_by_month": {}, "resolved_by_month": {}, "resolved_count": 0}
    uri = f"file:{source.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        feature_rows = connection.execute(
            "SELECT canonical_opportunity_id, timestamp_utc, feature_status FROM canonical_opportunities"
        ).fetchall()
        scorable: Counter[str] = Counter()
        for canonical_id, timestamp, status in feature_rows:
            if str(canonical_id) in canonical_ids and str(status).upper() != "CONFLICT":
                scorable[_month(str(timestamp))] += 1
        resolved_rows = connection.execute(
            """
            SELECT t.canonical_opportunity_id, t.timestamp_utc
            FROM trading_episodes t
            JOIN episode_outcomes o ON o.episode_id = t.episode_id
            WHERE o.resolved = 1 AND t.canonical_opportunity_id IS NOT NULL
            """
        ).fetchall()
        resolved_by_id: dict[str, str] = {}
        for canonical_id, timestamp in resolved_rows:
            if str(canonical_id) in canonical_ids:
                resolved_by_id.setdefault(str(canonical_id), _month(str(timestamp)))
        resolved: Counter[str] = Counter(resolved_by_id.values())
        return {
            "scorable_by_month": dict(sorted(scorable.items())),
            "resolved_by_month": dict(sorted(resolved.items())),
            "resolved_count": len(resolved_by_id),
        }
    finally:
        connection.close()


def _months_between(months: Iterable[str]) -> int:
    values = sorted(set(months))
    if not values:
        return 0
    first = datetime.strptime(values[0], "%Y-%m")
    last = datetime.strptime(values[-1], "%Y-%m")
    return (last.year - first.year) * 12 + last.month - first.month + 1


def build_coverage_report(
    repo_root: str | Path,
    *,
    phase1_db: str | Path | None = None,
    paths: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Chạy replay deterministic và trả report machine-readable."""

    source_paths = tuple(paths or discover_historical_audit_sources(repo_root))
    events = _load_events(source_paths)
    expected_ids = {canonical_opportunity_id(event) for event in events}
    observed_ids: list[str] = []
    payload_ids: Counter[str] = Counter()
    for event in events:
        payload = observation_payload_from_normalized(event)
        observation = validate_opportunity_payload(payload, source="historical-replay")
        evidence = canonicalize_observation(observation)
        observed_ids.append(evidence.canonical_opportunity_id)
        payload_ids[evidence.canonical_opportunity_id] += 1
    actual_ids = set(observed_ids)
    duplicates = sum(max(0, count - 1) for count in payload_ids.values())
    missing = sorted(expected_ids - actual_ids)
    unexpected = sorted(actual_ids - expected_ids)
    first_by_id: dict[str, str] = {}
    for event in events:
        first_by_id.setdefault(canonical_opportunity_id(event), event.event_time_utc)
    monthly_canonical = Counter(_month(timestamp) for timestamp in first_by_id.values())
    db_metrics = _phase1_db_metrics(
        phase1_db or Path(repo_root) / "data" / "phase1-validation-clean" / "phase1-validation-clean.sqlite",
        actual_ids,
    )
    months = _months_between(monthly_canonical)
    resolved_count = int(db_metrics["resolved_count"])
    resolved_months = _months_between(db_metrics["resolved_by_month"])
    months_for_rate = resolved_months or months
    resolved_rate = resolved_count / months_for_rate if months_for_rate else 0.0
    return {
        "report_schema": "phase3-telemetry-coverage/1",
        "actual_source": "authoritative_phase1_v81_v82_replay_through_new_observation_adapter",
        "source_paths": [str(path) for path in source_paths],
        "historical_validation_period": {
            "from_utc": min((event.event_time_utc for event in events), default=None),
            "to_utc": max((event.event_time_utc for event in events), default=None),
        },
        "phase1_dataset_fingerprint": PHASE1_DATASET_FINGERPRINT,
        "phase1_canonicalizer_version": "canonical-opportunity/1",
        "canonicalizer_fingerprint": CANONICALIZER_FINGERPRINT,
        "raw_observation_count": len(events),
        "expected_canonical_count": len(expected_ids),
        "actual_canonical_count": len(actual_ids),
        "missing_canonical_count": len(missing),
        "unexpected_canonical_count": len(unexpected),
        "raw_duplicate_collapse_count": duplicates,
        "duplicate_canonical_predictions": 0,
        "canonical_precision": len(actual_ids & expected_ids) / len(actual_ids) if actual_ids else 0.0,
        "canonical_recall": len(actual_ids & expected_ids) / len(expected_ids) if expected_ids else 0.0,
        "monthly_canonical_opportunities": dict(sorted(monthly_canonical.items())),
        "monthly_scorable_opportunities": db_metrics["scorable_by_month"],
        "monthly_resolved_label_opportunities": db_metrics["resolved_by_month"],
        "resolved_label_count": resolved_count,
        "resolved_label_rate_per_month": resolved_rate,
        "estimated_months_to_500_resolved": (500.0 / resolved_rate) if resolved_rate > 0 else None,
        "old_primary_monthly_rate": None,
        "old_primary_rate_status": "NOT_AVAILABLE_NO_SAVED_EXECUTION_CANDIDATE_STREAM",
        "coverage_multiplier": None,
        "missing_ids_sample": missing[:10],
        "unexpected_ids_sample": unexpected[:10],
        "mql_runtime_stream_generated": False,
        "mql_runtime_stream_note": "No FORWARD run was created; replay validates the producer contract without activation.",
        "live_execution_enabled": False,
        "forward_collection_status": "READY",
        "forward_run_id": "NOT_CREATED",
    }


def markdown_report(report: Mapping[str, Any]) -> str:
    """Render report reviewable, không đưa raw telemetry hoặc DB vào repo."""

    coverage_status = "PASS" if (
        report.get("missing_canonical_count") == 0
        and report.get("unexpected_canonical_count") == 0
        and report.get("duplicate_canonical_predictions") == 0
        and report.get("canonical_precision") == 1.0
        and report.get("canonical_recall") == 1.0
    ) else "FAIL"
    lines = [
        "# Phase 3.1 Telemetry Coverage",
        "",
        f"`CANONICAL_COVERAGE_STATUS`: **{coverage_status}**",
        "",
        "## Contract",
        "",
        "- Old stream: `phase3-live-telemetry/1` / `EXECUTION_CANDIDATE` (diagnostic-only).",
        "- New primary observation: `phase3-opportunity-observation/1`.",
        "- Internal evidence: `phase3-canonical-opportunity/1`.",
        "- Canonicalizer: existing `agent/data/normalization/canonical.py`, version `canonical-opportunity/1`.",
        f"- Phase 1 fingerprint: `{report.get('phase1_dataset_fingerprint')}` (unchanged contract evidence).",
        "",
        "## Historical deterministic replay",
        "",
        f"- Period: `{report['historical_validation_period']['from_utc']}` → `{report['historical_validation_period']['to_utc']}`.",
        f"- Raw observations: `{report.get('raw_observation_count')}`.",
        f"- Expected canonical opportunities: `{report.get('expected_canonical_count')}`.",
        f"- Actual canonical opportunities: `{report.get('actual_canonical_count')}`.",
        f"- Missing: `{report.get('missing_canonical_count')}`; unexpected: `{report.get('unexpected_canonical_count')}`.",
        f"- Raw duplicate collapse: `{report.get('raw_duplicate_collapse_count')}`; duplicate predictions: `{report.get('duplicate_canonical_predictions')}`.",
        f"- Precision: `{report.get('canonical_precision')}`; recall: `{report.get('canonical_recall')}`.",
        "",
        "The actual set in this report is a deterministic replay of the authoritative V81/V82 audit artifacts through the new raw-observation adapter. It is not a claim that a FORWARD source was activated; no FORWARD run was created.",
        "",
        "## Coverage rates",
        "",
        f"- New canonical opportunities/month: `{json.dumps(report.get('monthly_canonical_opportunities'), sort_keys=True)}`.",
        f"- Scorable opportunities/month: `{json.dumps(report.get('monthly_scorable_opportunities'), sort_keys=True)}`.",
        f"- Resolved-label opportunities/month: `{json.dumps(report.get('monthly_resolved_label_opportunities'), sort_keys=True)}`.",
        f"- Estimated months to 500 resolved labels: `{report.get('estimated_months_to_500_resolved')}`.",
        "- Old execution-candidate monthly rate: `NOT_AVAILABLE` because no saved old primary stream was found; no multiplier or old ETA is invented.",
        "",
        "## Safety",
        "",
        "- `LIVE_EXECUTION_ENABLED=NO`.",
        "- `FORWARD_COLLECTION_STATUS=READY`.",
        "- `FORWARD_RUN_ID=NOT_CREATED`.",
        "- No authorization, scheduler installation, or live activation is part of this coverage replay.",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "PHASE1_DATASET_FINGERPRINT",
    "build_coverage_report",
    "discover_historical_audit_sources",
    "markdown_report",
    "observation_payload_from_normalized",
]
