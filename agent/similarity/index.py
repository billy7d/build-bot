"""Expanding historical index; future rows never enter a query."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from ..data.normalization.timestamps import timestamp_to_datetime
from ..features.registry import FeatureLeakageError, is_outcome_field
from .distance import distance_with_overlap
from .models import Neighbor, SimilarityConfig, SimilarityResult


def _timestamp(value: Any) -> Any:
    parsed = timestamp_to_datetime(str(value))
    if parsed.tzinfo is None:
        raise ValueError("similarity timestamps must be timezone-aware UTC")
    return parsed


def _vector(row: Mapping[str, Any]) -> Mapping[str, Any] | list[float] | tuple[float, ...] | None:
    value = row.get("feature_vector")
    if value is None:
        value = row.get("features_normalized")
    if value is None:
        value = row.get("vector")
    if isinstance(value, Mapping):
        for key in value:
            if is_outcome_field(str(key)):
                raise FeatureLeakageError(f"outcome field rejected from feature vector: {key}")
    return value


def _metadata(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if key == "regime":
        nested = row.get("regime")
        if isinstance(nested, Mapping):
            return nested.get("composite_regime", default)
        if nested not in (None, ""):
            return nested
        return row.get("composite_regime", default)
    if key in row:
        return row[key]
    return default


def _label(row: Mapping[str, Any]) -> int | None:
    labels = row.get("labels")
    if isinstance(labels, Mapping):
        value = labels.get("plus_1r_before_minus_1r")
    else:
        value = row.get("plus_1r_before_minus_1r", row.get("label"))
    if value in (0, 1):
        return int(value)
    return None


def _expected(row: Mapping[str, Any]) -> float | None:
    labels = row.get("labels")
    value = labels.get("shadow_return_24bar_r") if isinstance(labels, Mapping) else row.get("expected_r_24bar", row.get("shadow_return_24bar_r"))
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _outcome_timestamp(row: Mapping[str, Any]) -> Any | None:
    labels = row.get("labels")
    value = labels.get("outcome_timestamp_utc") if isinstance(labels, Mapping) else row.get("outcome_timestamp_utc")
    return _timestamp(value) if value else None


def _outcome(row: Mapping[str, Any]) -> dict[str, Any] | None:
    label = _label(row)
    expected = _expected(row)
    labels = row.get("labels") if isinstance(row.get("labels"), Mapping) else {}
    if label is None and expected is None:
        return None
    return {
        "plus_1r_before_minus_1r": label,
        "expected_r_24bar": expected,
        "label_status": labels.get("label_status"),
        "outcome_timestamp_utc": labels.get("outcome_timestamp_utc", row.get("outcome_timestamp_utc")),
    }


class HistoricalSimilarityIndex:
    """An index whose contents are explicitly controlled by the caller.

    ``add`` is intentionally separate from ``query`` so expanding temporal
    evaluation cannot accidentally build one index from all dates.
    """

    def __init__(self, rows: Iterable[Mapping[str, Any]] | None = None, *, config: SimilarityConfig | None = None):
        self.config = config or SimilarityConfig()
        self._rows: dict[str, Mapping[str, Any]] = {}
        if rows:
            for row in rows:
                self.add(row)

    @property
    def rows(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._rows[key] for key in sorted(self._rows))

    def add(self, row: Mapping[str, Any], vector: Mapping[str, Any] | list[float] | tuple[float, ...] | None = None) -> None:
        identifier = str(row.get("canonical_opportunity_id") or "")
        if not identifier:
            raise ValueError("similarity row requires canonical_opportunity_id")
        if identifier in self._rows:
            raise ValueError(f"duplicate canonical id in similarity index: {identifier}")
        if "timestamp_utc" not in row:
            raise ValueError("similarity row requires timestamp_utc")
        _timestamp(row["timestamp_utc"])
        if vector is not None:
            row = {**dict(row), "feature_vector": vector}
        _vector(row)
        self._rows[identifier] = row

    def query(
        self,
        query_row: Mapping[str, Any],
        *,
        query_vector: Mapping[str, Any] | list[float] | tuple[float, ...] | None = None,
        as_of: str | None = None,
        config: SimilarityConfig | None = None,
    ) -> SimilarityResult:
        config = config or self.config
        query_id = str(query_row.get("canonical_opportunity_id") or "")
        query_row_time_value = query_row.get("timestamp_utc")
        query_time_value = as_of or query_row_time_value
        if not query_time_value:
            raise ValueError("query requires timestamp_utc/as_of")
        query_time = _timestamp(query_time_value)
        # ``as_of`` is a knowledge cutoff, never permission to use a neighbor
        # after the query event itself.
        if query_row_time_value:
            query_time = min(query_time, _timestamp(query_row_time_value))
        reported_query_timestamp = str(query_row_time_value or query_time_value)
        if str(query_row.get("feature_status", "")).upper() == "CONFLICT":
            return SimilarityResult(
                query_opportunity_id=query_id,
                query_timestamp_utc=reported_query_timestamp,
                neighbors=(),
                neighbor_count=0,
                effective_sample_size=0.0,
                historical_win_probability=None,
                historical_expected_r=None,
                confidence="NO_OPINION",
                opinion_status="NO_OPINION",
                reason="FEATURE_CONFLICT",
                filter_coverage={"query": 1},
                similarity_version=config.version,
            )
        vector = query_vector if query_vector is not None else _vector(query_row)
        if vector is None:
            return SimilarityResult(
                query_opportunity_id=query_id,
                query_timestamp_utc=reported_query_timestamp,
                neighbors=(),
                neighbor_count=0,
                effective_sample_size=0.0,
                historical_win_probability=None,
                historical_expected_r=None,
                confidence="NO_OPINION",
                opinion_status="NO_OPINION",
                reason="INSUFFICIENT_FEATURES",
                filter_coverage={"query": 1},
                similarity_version=config.version,
            )
        query_symbol = str(query_row.get("symbol") or "")
        query_timeframe = str(query_row.get("timeframe") or "")
        query_side = str(query_row.get("side") or "")
        query_regime = str(_metadata(query_row, "regime", "UNKNOWN") or "UNKNOWN")
        coverage = {"index_rows": len(self._rows), "past_timestamp": 0, "same_symbol": 0, "same_timeframe": 0, "compatible_side": 0, "compatible_regime": 0, "outcome_available": 0, "distance_eligible": 0}
        eligible: list[tuple[float, int, Mapping[str, Any]]] = []
        for identifier in sorted(self._rows):
            row = self._rows[identifier]
            if identifier == query_id:
                continue
            if str(row.get("feature_status", "")).upper() == "CONFLICT":
                continue
            candidate_time = _timestamp(row["timestamp_utc"])
            if not candidate_time < query_time:
                continue
            coverage["past_timestamp"] += 1
            if config.same_symbol and str(row.get("symbol") or "") != query_symbol:
                continue
            coverage["same_symbol"] += 1
            if config.same_timeframe and str(row.get("timeframe") or "") != query_timeframe:
                continue
            coverage["same_timeframe"] += 1
            if config.side_mode == "same" and str(row.get("side") or "") != query_side:
                continue
            coverage["compatible_side"] += 1
            candidate_regime = str(_metadata(row, "regime", "UNKNOWN") or "UNKNOWN")
            if config.regime_mode == "same_composite" and query_regime not in {"", "UNKNOWN"} and candidate_regime not in {query_regime, "UNKNOWN"}:
                continue
            coverage["compatible_regime"] += 1
            if config.require_outcome_available:
                available_at = _outcome_timestamp(row)
                # Without an outcome timestamp there is no auditable proof
                # that the label was known before the query.  Abstain from
                # treating such a row as historical support.
                if available_at is None or available_at >= query_time:
                    continue
            coverage["outcome_available"] += 1
            candidate_vector = _vector(row)
            if candidate_vector is None:
                continue
            distance, overlap = distance_with_overlap(vector, candidate_vector, min_overlap=config.min_feature_overlap)
            if distance is None:
                continue
            if config.max_distance is not None and distance > config.max_distance:
                continue
            coverage["distance_eligible"] += 1
            eligible.append((distance, overlap, row))
        eligible.sort(key=lambda item: (item[0], str(item[2].get("timestamp_utc", "")), str(item[2].get("canonical_opportunity_id", ""))))
        selected = eligible[: max(0, int(config.top_k))]
        neighbors: list[Neighbor] = []
        # Selection above uses only feature vectors and temporal/context
        # filters.  Historical outcomes are attached only after selection.
        for rank, (distance, overlap, row) in enumerate(selected, start=1):
            neighbors.append(
                Neighbor(
                    canonical_opportunity_id=str(row["canonical_opportunity_id"]),
                    timestamp_utc=str(row["timestamp_utc"]),
                    distance=float(distance),
                    regime=str(_metadata(row, "regime", "UNKNOWN") or "UNKNOWN"),
                    side=str(row.get("side") or "UNKNOWN"),
                    historical_outcome=_outcome(row),
                    rank=rank,
                    feature_overlap=overlap,
                )
            )
        outcome_neighbors = [item for item in neighbors if item.historical_outcome is not None]
        label_pairs = [
            (item.historical_outcome.get("plus_1r_before_minus_1r"), item.distance)
            for item in outcome_neighbors
            if item.historical_outcome.get("plus_1r_before_minus_1r") in (0, 1)
        ]
        expected_pairs = [
            (item.historical_outcome.get("expected_r_24bar"), item.distance)
            for item in outcome_neighbors
            if isinstance(item.historical_outcome.get("expected_r_24bar"), (int, float))
        ]
        labels = [int(value) for value, _ in label_pairs]
        expected = [float(value) for value, _ in expected_pairs]
        if coverage["distance_eligible"] == 0 and coverage["outcome_available"] > 0:
            status, reason = "NO_OPINION", "INSUFFICIENT_FEATURES"
        elif config.regime_mode == "same_composite" and query_regime not in {"", "UNKNOWN"} and coverage["compatible_regime"] == 0:
            status, reason = "NO_OPINION", "NO_COMPATIBLE_REGIME"
        elif len(selected) < config.min_neighbors:
            status, reason = "NO_OPINION", "INSUFFICIENT_HISTORY"
        elif len(outcome_neighbors) < config.min_neighbors:
            status, reason = "NO_OPINION", "LOW_EFFECTIVE_SAMPLE"
        elif not labels and not expected:
            status, reason = "NO_OPINION", "INSUFFICIENT_FEATURES"
        else:
            status, reason = "OK", "SUPPORTED"
        weights = [1.0 / max(item.distance, 1e-9) for item in outcome_neighbors]
        weight_sum = sum(weights)
        effective_size = (weight_sum * weight_sum / sum(weight * weight for weight in weights)) if weights else 0.0
        label_weights = [1.0 / max(distance, 1e-9) for _, distance in label_pairs]
        expected_weights = [1.0 / max(distance, 1e-9) for _, distance in expected_pairs]
        probability = sum(label * weight for label, weight in zip(labels, label_weights)) / sum(label_weights) if labels and sum(label_weights) else None
        expected_r = sum(value * weight for value, weight in zip(expected, expected_weights)) / sum(expected_weights) if expected and sum(expected_weights) else None
        if status != "OK":
            confidence = "NO_OPINION"
        elif effective_size >= max(10, config.min_neighbors * 2) and (not selected or selected[0][0] <= 3.0):
            confidence = "HIGH"
        elif effective_size >= config.min_neighbors:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        return SimilarityResult(
            query_opportunity_id=query_id,
            query_timestamp_utc=reported_query_timestamp,
            neighbors=tuple(neighbors),
            neighbor_count=len(neighbors),
            effective_sample_size=effective_size,
            historical_win_probability=probability,
            historical_expected_r=expected_r,
            confidence=confidence,
            opinion_status=status,
            reason=reason,
            filter_coverage=coverage,
            similarity_version=config.version,
        )


def evaluate_temporal_similarity(
    rows: Iterable[Mapping[str, Any]],
    vectors: Mapping[str, Mapping[str, Any] | list[float] | tuple[float, ...]],
    *,
    splits: Mapping[str, str] | None = None,
    config: SimilarityConfig | None = None,
    evaluation_splits: set[str] | None = None,
) -> dict[str, SimilarityResult]:
    """Run an expanding index where each query sees only earlier rows."""

    config = config or SimilarityConfig()
    records = sorted(rows, key=lambda row: (str(row.get("timestamp_utc", "")), str(row.get("canonical_opportunity_id", ""))))
    index = HistoricalSimilarityIndex(config=config)
    results: dict[str, SimilarityResult] = {}
    wanted = evaluation_splits or {"VALIDATION", "OOS"}
    for row in records:
        identifier = str(row.get("canonical_opportunity_id"))
        split = splits.get(identifier) if splits else None
        if split in wanted:
            result = index.query(row, query_vector=vectors.get(identifier), config=config)
            results[identifier] = result
        index.add(row, vectors.get(identifier))
    return results


__all__ = ["HistoricalSimilarityIndex", "evaluate_temporal_similarity"]
