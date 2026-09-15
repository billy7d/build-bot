"""Health và drift monitoring chỉ quan sát, không tự retrain/điều khiển."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from typing import Any, Iterable, Mapping

from ..features.registry import FEATURE_ALLOWLIST
from .models import HealthSnapshot, utc_now


class HealthTracker:
    """Bộ đếm runtime có thể snapshot deterministically."""

    def __init__(self) -> None:
        self._snapshot = HealthSnapshot()

    @property
    def snapshot(self) -> HealthSnapshot:
        return self._snapshot

    def received(self, timestamp_utc: str | None = None) -> None:
        self._snapshot = replace(self._snapshot, events_received=self._snapshot.events_received + 1, last_ingest_utc=timestamp_utc or utc_now())

    def accepted(self) -> None:
        self._snapshot = replace(self._snapshot, events_accepted=self._snapshot.events_accepted + 1)

    def rejected(self, *, schema: bool = False) -> None:
        self._snapshot = replace(
            self._snapshot,
            events_rejected=self._snapshot.events_rejected + 1,
            schema_errors=self._snapshot.schema_errors + (1 if schema else 0),
        )

    def duplicate(self) -> None:
        self._snapshot = replace(self._snapshot, duplicates=self._snapshot.duplicates + 1)

    def out_of_order_event(self) -> None:
        self._snapshot = replace(self._snapshot, out_of_order=self._snapshot.out_of_order + 1)

    def prediction(self, created_at_utc: str | None = None, *, no_opinion: bool = False, latency_ms: float | None = None) -> None:
        latencies = self._snapshot.processing_latencies_ms
        if latency_ms is not None:
            latencies = (*latencies[-999:], float(latency_ms))
        self._snapshot = replace(
            self._snapshot,
            predictions=self._snapshot.predictions + 1,
            no_opinion=self._snapshot.no_opinion + (1 if no_opinion else 0),
            last_prediction_utc=created_at_utc or utc_now(),
            processing_latencies_ms=latencies,
        )

    def feature_quality(self, *, missing: bool = False, ood: bool = False) -> None:
        """Ghi chất lượng feature của prediction mà không thay đổi dữ liệu."""

        self._snapshot = replace(
            self._snapshot,
            missing_feature_events=self._snapshot.missing_feature_events + (1 if missing else 0),
            ood_events=self._snapshot.ood_events + (1 if ood else 0),
        )

    def pending(self, count: int = 1) -> None:
        self._snapshot = replace(self._snapshot, pending_outcomes=self._snapshot.pending_outcomes + count)

    def sync_pending(self, count: int) -> None:
        """Đồng bộ backlog từ SQLite sau khi process được restart."""

        self._snapshot = replace(self._snapshot, pending_outcomes=max(0, int(count)))

    def resolved(self, *, incomplete: bool = False) -> None:
        self._snapshot = replace(
            self._snapshot,
            pending_outcomes=max(0, self._snapshot.pending_outcomes - 1),
            resolved_outcomes=self._snapshot.resolved_outcomes + (0 if incomplete else 1),
            incomplete_outcomes=self._snapshot.incomplete_outcomes + (1 if incomplete else 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return self._snapshot.to_dict()


def persist_health_event(connection: Any, run_id: str | None, event_type: str, value: Mapping[str, Any], *, severity: str = "INFO", created_at_utc: str | None = None) -> None:
    """Ghi telemetry health dạng append-only event."""

    connection.execute(
        "INSERT INTO phase3_health_events(run_id, event_type, severity, value_json, created_at_utc) VALUES (?, ?, ?, ?, ?)",
        (run_id, event_type, severity, json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")), created_at_utc or utc_now()),
    )


def _values(rows: Iterable[Mapping[str, Any]], name: str) -> list[Any]:
    result: list[Any] = []
    for row in rows:
        nested = row.get("features")
        if isinstance(nested, Mapping) and name in nested:
            result.append(nested[name])
        elif name in row:
            result.append(row[name])
        else:
            result.append(None)
    return result


def _categorical_distribution(rows: Iterable[Mapping[str, Any]], *names: str) -> dict[str, int]:
    """Chuẩn hóa một nhóm field health về distribution reviewable."""

    values: list[str] = []
    for row in rows:
        value: Any = None
        for name in names:
            if name in row:
                value = row.get(name)
                break
        if value is None and isinstance(row.get("ood_inputs"), Mapping) and "is_ood" in row["ood_inputs"]:
            value = "OUT_OF_DISTRIBUTION" if row["ood_inputs"].get("is_ood") else "IN_DISTRIBUTION"
        values.append(str(value or "UNKNOWN").upper())
    return dict(sorted(Counter(values).items()))


def _similarity_distances(rows: Iterable[Mapping[str, Any]]) -> list[float]:
    """Lấy distance từ snapshot, không query lại historical reference."""

    distances: list[float] = []
    for row in rows:
        direct = row.get("similarity_distance")
        if isinstance(direct, (int, float)) and not isinstance(direct, bool):
            distances.append(float(direct))
            continue
        summary = row.get("similarity_summary")
        if not isinstance(summary, Mapping):
            continue
        neighbors = summary.get("neighbors")
        if not isinstance(neighbors, (list, tuple)):
            continue
        for neighbor in neighbors:
            if not isinstance(neighbor, Mapping):
                continue
            value = neighbor.get("distance")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                distances.append(float(value))
    return distances


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _feature_drift(historical: list[Mapping[str, Any]], forward: list[Mapping[str, Any]], names: Iterable[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    largest = 0.0
    for name in names:
        old = _values(historical, name)
        new = _values(forward, name)
        old_present = [float(item) for item in old if isinstance(item, (int, float)) and not isinstance(item, bool)]
        new_present = [float(item) for item in new if isinstance(item, (int, float)) and not isinstance(item, bool)]
        old_missing = 1.0 - (len(old_present) / len(old) if old else 0.0)
        new_missing = 1.0 - (len(new_present) / len(new) if new else 0.0)
        missing_delta = abs(new_missing - old_missing)
        old_q = [_quantile(old_present, p) for p in (0.1, 0.5, 0.9)]
        new_q = [_quantile(new_present, p) for p in (0.1, 0.5, 0.9)]
        scales = [abs(a) for a in old_q + new_q if a is not None]
        scale = max(max(scales, default=1.0), 1.0)
        quantile_delta = max((abs(a - b) / scale for a, b in zip(old_q, new_q) if a is not None and b is not None), default=0.0)
        score = max(missing_delta, quantile_delta)
        largest = max(largest, score)
        values[name] = {
            "historical_missing_rate": round(old_missing, 8),
            "forward_missing_rate": round(new_missing, 8),
            "missing_rate_delta": round(missing_delta, 8),
            "historical_quantiles": old_q,
            "forward_quantiles": new_q,
            "normalized_quantile_delta": round(quantile_delta, 8),
        }
    return {"features": values, "largest_feature_drift": round(largest, 8)}


def detect_drift(
    historical_rows: Iterable[Mapping[str, Any]],
    forward_rows: Iterable[Mapping[str, Any]],
    *,
    feature_names: Iterable[str] = FEATURE_ALLOWLIST,
    warning_threshold: float = 0.10,
    severe_threshold: float = 0.25,
) -> dict[str, Any]:
    """So sánh feature/OOD/similarity/side/regime/confidence, không update model."""

    historical = list(historical_rows)
    forward = list(forward_rows)
    feature = _feature_drift(historical, forward, sorted(set(feature_names)))
    historical_side = Counter(str(row.get("side") or "UNKNOWN") for row in historical)
    forward_side = Counter(str(row.get("side") or "UNKNOWN") for row in forward)
    historical_regime = Counter(str(row.get("regime") or "UNKNOWN") for row in historical)
    forward_regime = Counter(str(row.get("regime") or "UNKNOWN") for row in forward)
    historical_ood = _categorical_distribution(historical, "ood_status", "ood_state")
    forward_ood = _categorical_distribution(forward, "ood_status", "ood_state")
    historical_confidence = _categorical_distribution(historical, "confidence", "model_confidence")
    forward_confidence = _categorical_distribution(forward, "confidence", "model_confidence")
    historical_similarity_distances = _similarity_distances(historical)
    forward_similarity_distances = _similarity_distances(forward)
    historical_distance_q = [_quantile(historical_similarity_distances, p) for p in (0.1, 0.5, 0.9)]
    forward_distance_q = [_quantile(forward_similarity_distances, p) for p in (0.1, 0.5, 0.9)]
    distance_scales = [abs(value) for value in historical_distance_q + forward_distance_q if value is not None]
    distance_scale = max(max(distance_scales, default=1.0), 1.0)
    distance_delta = max(
        (abs(old - new) / distance_scale for old, new in zip(historical_distance_q, forward_distance_q) if old is not None and new is not None),
        default=0.0,
    )
    distribution_shift = any(
        old != new
        for old, new in (
            (dict(historical_side), dict(forward_side)),
            (dict(historical_regime), dict(forward_regime)),
            (historical_ood, forward_ood),
            (historical_confidence, forward_confidence),
        )
    )
    largest_drift = max(float(feature["largest_feature_drift"]), distance_delta)
    if not forward:
        status = "DRIFT_OK"
    elif largest_drift >= severe_threshold:
        status = "DRIFT_SEVERE"
    elif largest_drift >= warning_threshold or distribution_shift:
        status = "DRIFT_WARNING"
    else:
        status = "DRIFT_OK"
    return {
        "status": status,
        "historical_count": len(historical),
        "forward_count": len(forward),
        "feature_drift": feature,
        "historical_side_distribution": dict(sorted(historical_side.items())),
        "forward_side_distribution": dict(sorted(forward_side.items())),
        "historical_regime_distribution": dict(sorted(historical_regime.items())),
        "forward_regime_distribution": dict(sorted(forward_regime.items())),
        "historical_ood_distribution": historical_ood,
        "forward_ood_distribution": forward_ood,
        "historical_confidence_distribution": historical_confidence,
        "forward_confidence_distribution": forward_confidence,
        "similarity_distance": {
            "historical_count": len(historical_similarity_distances),
            "forward_count": len(forward_similarity_distances),
            "historical_quantiles": historical_distance_q,
            "forward_quantiles": forward_distance_q,
            "normalized_quantile_delta": round(distance_delta, 8),
        },
        "largest_drift_score": round(largest_drift, 8),
        "auto_retrain": False,
        "auto_reference_update": False,
    }


__all__ = ["HealthTracker", "detect_drift", "persist_health_event"]
