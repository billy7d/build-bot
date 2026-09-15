"""Metrics cố định cho forward evidence, không tuning theo kết quả."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from ...scoring.calibration import classification_metrics
from ...scoring.validation import regression_metrics
from ..models import parse_utc_timestamp
from .bootstrap import block_bootstrap_ci


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _valid_records(records: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for record in records:
        if str(record.get("run_mode", "FORWARD")).upper() != "FORWARD":
            continue
        if int(record.get("forward_valid", 1) or 0) != 1:
            continue
        if str(record.get("outcome_status", "")).upper() != "RESOLVED":
            continue
        try:
            if parse_utc_timestamp(str(record["prediction_committed_at_utc"])) >= parse_utc_timestamp(str(record["outcome_observed_at_utc"])):
                continue
        except (KeyError, ValueError):
            continue
        result.append(record)
    return result


def _prior_probability(records: list[Mapping[str, Any]], key: str | None = None) -> list[float | None]:
    groups: dict[str, list[int]] = defaultdict(list)
    for record in records:
        label = record.get("classification_label")
        if label not in (0, 1):
            continue
        group = str(record.get(key, "UNKNOWN")) if key else "ALL"
        groups[group].append(int(label))
    overall = [int(record["classification_label"]) for record in records if record.get("classification_label") in (0, 1)]
    fallback = sum(overall) / len(overall) if overall else None
    result: list[float | None] = []
    for record in records:
        group = str(record.get(key, "UNKNOWN")) if key else "ALL"
        labels = groups.get(group)
        result.append(sum(labels) / len(labels) if labels else fallback)
    return result


def _prior_expected(records: list[Mapping[str, Any]], key: str | None = None) -> list[float | None]:
    groups: dict[str, list[float]] = defaultdict(list)
    for record in records:
        value = _number(record.get("return_24bar_r"))
        if value is not None:
            groups[str(record.get(key, "UNKNOWN")) if key else "ALL"].append(value)
    all_values = [value for values in groups.values() for value in values]
    fallback = sum(all_values) / len(all_values) if all_values else None
    return [
        (sum(groups.get(str(record.get(key, "UNKNOWN")) if key else "ALL", ())) / len(groups.get(str(record.get(key, "UNKNOWN")) if key else "ALL", ()))
         if groups.get(str(record.get(key, "UNKNOWN")) if key else "ALL") else fallback)
        for record in records
    ]


def _metric_with_values(labels: list[int], predictions: list[float | None]) -> dict[str, Any]:
    aligned = [(label, float(value)) for label, value in zip(labels, predictions) if value is not None and math.isfinite(float(value))]
    if not aligned:
        return classification_metrics([], [])
    return classification_metrics([item[0] for item in aligned], [item[1] for item in aligned])


def _metric_with_records(
    records: list[Mapping[str, Any]],
    predictions: list[float | None],
) -> dict[str, Any]:
    """Ghép label và prediction theo cùng record, kể cả khi label bị thiếu."""

    aligned: list[tuple[int, float]] = []
    for record, prediction in zip(records, predictions):
        label = record.get("classification_label")
        value = _number(prediction)
        if label in (0, 1) and value is not None:
            aligned.append((int(label), value))
    if not aligned:
        return classification_metrics([], [])
    return classification_metrics(
        [label for label, _ in aligned],
        [value for _, value in aligned],
    )


def _aligned_regression(
    realized: list[float | None],
    predicted: list[float | None],
) -> tuple[list[float], list[float]]:
    """Giữ đúng cặp outcome/prediction, không làm lệch hai vector khi thiếu giá trị."""

    pairs = [
        (float(actual), float(forecast))
        for actual, forecast in zip(realized, predicted)
        if actual is not None and forecast is not None
    ]
    return [actual for actual, _ in pairs], [forecast for _, forecast in pairs]


def evaluate_forward_records(
    records: Iterable[Mapping[str, Any]],
    *,
    classification_min_resolved: int = 500,
    regression_min_resolved: int = 500,
    bootstrap_iterations: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Tính baseline/model metrics cố định và status evidence."""

    resolved = _valid_records(records)
    labels = [int(record["classification_label"]) for record in resolved if record.get("classification_label") in (0, 1)]
    model_probability = [record.get("probability_plus1_before_minus1") for record in resolved]
    prior_probability = _prior_probability(resolved)
    regime_probability = _prior_probability(resolved, "regime")
    similarity_probability = [
        record.get("similarity_probability") if record.get("similarity_probability") is not None else record.get("historical_win_probability")
        for record in resolved
    ]
    classification = {
        "logistic_phase2": _metric_with_records(resolved, model_probability),
        "unconditional_prior": _metric_with_records(resolved, prior_probability),
        "regime_prior": _metric_with_records(resolved, regime_probability),
        "historical_similarity": _metric_with_records(resolved, similarity_probability),
    }
    model_brier = classification["logistic_phase2"].get("brier_score")
    prior_brier = classification["unconditional_prior"].get("brier_score")
    brier_improvement = prior_brier - model_brier if model_brier is not None and prior_brier is not None else None
    realized = [_number(record.get("return_24bar_r")) for record in resolved]
    predicted = [_number(record.get("expected_return_24bar_r")) for record in resolved]
    regression_actual, regression_forecast = _aligned_regression(realized, predicted)
    prior_actual, prior_forecast = _aligned_regression(realized, _prior_expected(resolved))
    regression = {
        "ridge_phase2": regression_metrics(regression_actual, regression_forecast),
        "unconditional_expected_r": regression_metrics(prior_actual, prior_forecast),
    }
    regression_values = [(x, y) for x, y in zip(realized, predicted) if x is not None and y is not None]
    mae_improvement = None
    rmse_improvement = None
    if regression["ridge_phase2"].get("mae") is not None and regression["unconditional_expected_r"].get("mae") is not None:
        mae_improvement = regression["unconditional_expected_r"]["mae"] - regression["ridge_phase2"]["mae"]
    if regression["ridge_phase2"].get("rmse") is not None and regression["unconditional_expected_r"].get("rmse") is not None:
        rmse_improvement = regression["unconditional_expected_r"]["rmse"] - regression["ridge_phase2"]["rmse"]
    coverage = {
        "calendar_start": min((str(record.get("source_event_timestamp_utc")) for record in resolved), default=None),
        "calendar_end": max((str(record.get("source_event_timestamp_utc")) for record in resolved), default=None),
        "sides": dict(sorted(Counter(str(record.get("side", "UNKNOWN")) for record in resolved).items())),
        "regimes": dict(sorted(Counter(str(record.get("regime", "UNKNOWN")) for record in resolved).items())),
        "markets": dict(sorted(Counter(f"{record.get('symbol', 'UNKNOWN')}:{record.get('timeframe', 'UNKNOWN')}" for record in resolved).items())),
    }
    broad_coverage = len(coverage["sides"]) >= 2 and len(coverage["regimes"]) >= 2 and len(coverage["markets"]) >= 1
    enough_classification = len(labels) >= classification_min_resolved and broad_coverage
    enough_regression = len(regression_values) >= regression_min_resolved and broad_coverage
    if not enough_classification and not enough_regression:
        edge_status = "INSUFFICIENT_DATA"
    elif brier_improvement is not None and brier_improvement > 0 and enough_classification:
        edge_status = "WEAK"
    else:
        edge_status = "NOT_DEMONSTRATED"
    brier_deltas = []
    for index, record in enumerate(resolved):
        label = record.get("classification_label")
        probability = _number(record.get("probability_plus1_before_minus1"))
        prior = _number(prior_probability[index]) if index < len(prior_probability) else None
        if label in (0, 1) and probability is not None and prior is not None:
            brier_deltas.append((prior - int(label)) ** 2 - (probability - int(label)) ** 2)
    ci = block_bootstrap_ci(brier_deltas, lambda values: sum(values) / len(values) if values else 0.0, iterations=bootstrap_iterations, seed=seed) if brier_deltas else {"count": 0, "estimate": None, "lower_95": None, "upper_95": None}
    return {
        "schema": "trading_agent_phase3_forward_validation_v1",
        "resolved_sample_count": len(resolved),
        "classification_resolved_count": len(labels),
        "regression_24bar_resolved_count": len(regression_values),
        "classification": classification,
        "regression": regression,
        "improvements": {"brier": brier_improvement, "mae": mae_improvement, "rmse": rmse_improvement},
        "confidence_intervals": {"brier_improvement": ci},
        "coverage": coverage,
        "coverage_sufficient": broad_coverage,
        "forward_collection_status": "NO_DATA" if not resolved else "INSUFFICIENT_DATA" if not (enough_classification or enough_regression) else "SUFFICIENT_FOR_EVALUATION",
        "forward_predictive_edge_status": edge_status,
        "baselines_predeclared": ["unconditional_prior", "regime_prior", "historical_similarity", "logistic_phase2", "unconditional_expected_r", "ridge_phase2"],
        "outcome_used_for_model_fit": False,
        "auto_retrain": False,
        "auto_update_similarity_reference": False,
    }


__all__ = ["evaluate_forward_records"]
