"""Các kiểu dữ liệu và hằng số dùng chung cho Trading Agent Phase 3."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping

from ..features.fingerprint import canonical_json
from ..features.registry import FEATURE_ALLOWLIST


PHASE3_TELEMETRY_SCHEMA = "phase3-live-telemetry/1"
PHASE3_BUNDLE_VERSION = "phase3-shadow-bundle/1"
PHASE3_FEATURE_SNAPSHOT_VERSION = "phase3-feature-snapshot/1"
PHASE3_OUTCOME_SCHEMA_VERSION = "phase3-outcome/1"

RUN_MODES = frozenset({"SMOKE", "REPLAY", "FORWARD"})
RUN_STATUSES = frozenset({"CREATED", "RUNNING", "PAUSED", "STOPPED", "FAILED"})
EVENT_LIFECYCLE = (
    "RECEIVED",
    "VALIDATED",
    "CANONICALIZED",
    "FEATURED",
    "SCORED",
    "PREDICTION_COMMITTED",
    "OUTCOME_PENDING",
    "OUTCOME_RESOLVED",
)
FAILURE_STATES = frozenset({
    "REJECTED_SCHEMA",
    "REJECTED_DUPLICATE",
    "REJECTED_STALE",
    "REJECTED_CONFLICT",
    "NO_OPINION",
    "INCOMPLETE_OUTCOME",
})
OUTCOME_STATUSES = frozenset({"PENDING", "RESOLVED", "INCOMPLETE", "EXPIRED", "INVALID"})


def parse_utc_timestamp(value: str | datetime) -> datetime:
    """Parse timestamp có timezone và chuẩn hóa về UTC."""

    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include an explicit timezone")
    return parsed.astimezone(UTC)


def format_utc_timestamp(value: str | datetime) -> str:
    """Trả timestamp ISO UTC ổn định cho storage và fingerprint."""

    parsed = parse_utc_timestamp(value)
    timespec = "microseconds" if parsed.microsecond else "seconds"
    return parsed.isoformat(timespec=timespec).replace("+00:00", "Z")


def utc_now() -> str:
    return format_utc_timestamp(datetime.now(UTC))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def finite_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _feature_values(context: Mapping[str, Any]) -> dict[str, Any]:
    """Lấy đúng feature namespace, không kéo outcome vào vector."""

    nested = context.get("features")
    values: dict[str, Any] = dict(nested) if isinstance(nested, Mapping) else {}
    for name in FEATURE_ALLOWLIST:
        if name in context:
            values[name] = context[name]
    return {str(key): values[key] for key in sorted(values)}


@dataclass(frozen=True)
class TelemetryEvent:
    """Payload đã validate, vẫn giữ raw evidence để hash/audit."""

    schema_version: str
    source_event_id: str
    event_timestamp_utc: str
    symbol: str
    timeframe: str
    side: str
    context: Mapping[str, Any]
    source: str
    received_at_utc: str
    raw_payload: Mapping[str, Any]
    candidate_type: str = "UNKNOWN"
    bar_state: str = "closed_bar"
    available_at_utc: str | None = None
    source_timezone: str | None = None

    @property
    def features(self) -> dict[str, Any]:
        return _feature_values(self.context)

    @property
    def raw_payload_sha256(self) -> str:
        return sha256_json(self.raw_payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_event_id": self.source_event_id,
            "event_timestamp": self.event_timestamp_utc,
            "event_timestamp_utc": self.event_timestamp_utc,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "side": self.side,
            "context": dict(self.context),
            "source": self.source,
            "received_at_utc": self.received_at_utc,
            "candidate_type": self.candidate_type,
            "bar_state": self.bar_state,
            "available_at_utc": self.available_at_utc,
            "source_timezone": self.source_timezone,
            "raw_payload_sha256": self.raw_payload_sha256,
        }


@dataclass(frozen=True)
class FeatureSnapshot:
    """Snapshot feature bất biến tại thời điểm scoring."""

    feature_set_version: str
    feature_timestamp_utc: str
    feature_fingerprint: str
    feature_values: Mapping[str, Any]
    missingness: Mapping[str, bool]
    ood_inputs: Mapping[str, Any]
    created_at_utc: str
    vector: tuple[float, ...] = ()
    output_names: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["vector"] = list(self.vector)
        value["output_names"] = list(self.output_names)
        return value


@dataclass(frozen=True)
class OutcomeResolution:
    """Kết quả resolver; incomplete không bị biến thành loss."""

    status: str
    classification_label: int | None
    return_6bar_r: float | None
    return_12bar_r: float | None
    return_24bar_r: float | None
    return_48bar_r: float | None
    mfe_r: float | None
    mae_r: float | None
    resolved_at_utc: str | None
    outcome_observed_at_utc: str | None
    incomplete_reason: str | None
    outcome_schema_version: str = PHASE3_OUTCOME_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HealthSnapshot:
    """Counters bounded trong memory, có thể persist như một health event."""

    events_received: int = 0
    events_accepted: int = 0
    events_rejected: int = 0
    duplicates: int = 0
    out_of_order: int = 0
    schema_errors: int = 0
    predictions: int = 0
    pending_outcomes: int = 0
    resolved_outcomes: int = 0
    incomplete_outcomes: int = 0
    no_opinion: int = 0
    missing_feature_events: int = 0
    ood_events: int = 0
    last_ingest_utc: str | None = None
    last_prediction_utc: str | None = None
    processing_latencies_ms: tuple[float, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["processing_latencies_ms"] = list(self.processing_latencies_ms)
        # Tỷ lệ được tính từ prediction count để không trộn rejection với
        # chất lượng feature của những event đã qua schema gate.
        value["acceptance_rate"] = (
            self.events_accepted / self.events_received
            if self.events_received
            else None
        )
        value["schema_error_rate"] = (
            self.schema_errors / self.events_received
            if self.events_received
            else None
        )
        value["missing_feature_rate"] = (
            self.missing_feature_events / self.predictions
            if self.predictions
            else None
        )
        value["ood_rate"] = (
            self.ood_events / self.predictions
            if self.predictions
            else None
        )
        value["no_opinion_rate"] = (
            self.no_opinion / self.predictions
            if self.predictions
            else None
        )
        value["outcome_backlog"] = self.pending_outcomes
        ordered = sorted(self.processing_latencies_ms)
        if ordered:
            value["latency_p50_ms"] = ordered[(len(ordered) - 1) * 50 // 100]
            value["latency_p95_ms"] = ordered[(len(ordered) - 1) * 95 // 100]
            value["latency_max_ms"] = ordered[-1]
        else:
            value["latency_p50_ms"] = None
            value["latency_p95_ms"] = None
            value["latency_max_ms"] = None
        return value


__all__ = [
    "EVENT_LIFECYCLE",
    "FAILURE_STATES",
    "FeatureSnapshot",
    "HealthSnapshot",
    "OUTCOME_STATUSES",
    "PHASE3_BUNDLE_VERSION",
    "PHASE3_FEATURE_SNAPSHOT_VERSION",
    "PHASE3_OUTCOME_SCHEMA_VERSION",
    "PHASE3_TELEMETRY_SCHEMA",
    "OutcomeResolution",
    "RUN_MODES",
    "RUN_STATUSES",
    "TelemetryEvent",
    "finite_float",
    "format_utc_timestamp",
    "parse_utc_timestamp",
    "sha256_bytes",
    "sha256_json",
    "utc_now",
]
