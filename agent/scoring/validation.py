"""Leakage-safe validation, baseline comparison and walk-forward evaluation."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping

from ..data.normalization.timestamps import timestamp_to_datetime
from ..features.normalization import TrainOnlyPreprocessor
from ..similarity.models import SimilarityResult
from .baseline import prior_prediction
from .calibration import classification_metrics
from .labels import DIAGNOSTIC_TARGETS, build_diagnostic_target, build_expected_r_label, build_label
from .models import fit_logistic_regression, fit_ridge_regression
from .predict import score_opportunity
from .train import ModelBundle, ModelConfig


def regression_metrics(realized: list[float], predicted: list[float]) -> dict[str, Any]:
    if not realized or len(realized) != len(predicted):
        return {"count": 0, "mae": None, "rmse": None, "median_absolute_error": None, "spearman_rank_correlation": None, "mean_predicted_r": None, "mean_realized_r": None}
    errors = [prediction - actual for actual, prediction in zip(realized, predicted)]
    absolute = sorted(abs(error) for error in errors)
    squared = sum(error * error for error in errors)
    return {
        "count": len(realized),
        "mae": sum(abs(error) for error in errors) / len(errors),
        "rmse": math.sqrt(squared / len(errors)),
        "median_absolute_error": absolute[len(absolute) // 2] if len(absolute) % 2 else (absolute[len(absolute) // 2 - 1] + absolute[len(absolute) // 2]) / 2.0,
        "spearman_rank_correlation": _spearman(realized, predicted),
        "mean_predicted_r": sum(predicted) / len(predicted),
        "mean_realized_r": sum(realized) / len(realized),
    }


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=lambda index: (values[index], index))
    result = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[index]]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for position in ordered[index:end]:
            result[position] = rank
        index = end
    return result


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2:
        return None
    left_rank, right_rank = _ranks(left), _ranks(right)
    left_mean, right_mean = sum(left_rank) / len(left_rank), sum(right_rank) / len(right_rank)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_rank, right_rank))
    denominator_left = math.sqrt(sum((a - left_mean) ** 2 for a in left_rank))
    denominator_right = math.sqrt(sum((b - right_mean) ** 2 for b in right_rank))
    if denominator_left == 0.0 or denominator_right == 0.0:
        return None
    return numerator / (denominator_left * denominator_right)


def _split_records(rows: Iterable[Mapping[str, Any]], split: str, splits: Mapping[str, str]) -> list[Mapping[str, Any]]:
    return sorted(
        [row for row in rows if splits.get(str(row.get("canonical_opportunity_id"))) == split],
        key=lambda row: (str(row.get("timestamp_utc", "")), str(row.get("canonical_opportunity_id", ""))),
    )


def _classification_payload(labels: list[int], probabilities: list[float]) -> dict[str, Any]:
    return classification_metrics(labels, probabilities) if labels else classification_metrics([], [])


def _grouped_regression(
    records: list[tuple[Mapping[str, Any], float, float]],
    key_fn: Any,
) -> dict[str, Any]:
    groups: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for row, actual, prediction in records:
        key = str(key_fn(row))
        groups[key][0].append(actual)
        groups[key][1].append(prediction)
    return {key: regression_metrics(values[0], values[1]) for key, values in sorted(groups.items())}


def evaluate_models(
    rows: Iterable[Mapping[str, Any]],
    splits: Mapping[str, str],
    bundle: ModelBundle,
    *,
    regimes: Mapping[str, Any] | None = None,
    similarities: Mapping[str, SimilarityResult | Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    records = sorted(rows, key=lambda row: (str(row.get("timestamp_utc", "")), str(row.get("canonical_opportunity_id", ""))))
    identifiers = [str(row.get("canonical_opportunity_id") or "") for row in records]
    if any(not identifier for identifier in identifiers):
        raise ValueError("model evaluation input requires canonical_opportunity_id")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("model evaluation input contains duplicate canonical samples")
    regimes = regimes or {}
    similarities = similarities or {}
    by_split: dict[str, Any] = {}
    all_prediction_rows: list[dict[str, Any]] = []
    for split in ("VALIDATION", "OOS"):
        evaluation_rows = _split_records(records, split, splits)
        classification: dict[str, tuple[list[int], list[float]]] = defaultdict(lambda: ([], []))
        regression: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
        diagnostic_targets: dict[str, list[float]] = defaultdict(list)
        breakdown_records: list[tuple[Mapping[str, Any], float, float]] = []
        for row in evaluation_rows:
            identifier = str(row.get("canonical_opportunity_id"))
            label = build_label(row)
            expected = build_expected_r_label(row)
            for target in DIAGNOSTIC_TARGETS:
                diagnostic = build_diagnostic_target(row, target)
                if diagnostic is not None:
                    diagnostic_targets[target].append(float(diagnostic))
            score = score_opportunity(row, bundle, regime=regimes.get(identifier), similarity=similarities.get(identifier))
            vector = bundle.preprocessor.transform_one(row)
            if score.score_status == "OK" and bundle.logistic is not None and label in (0, 1):
                probability = bundle.calibrator.transform(bundle.logistic.predict_proba(vector))
                classification["logistic_regression"][0].append(int(label))
                classification["logistic_regression"][1].append(probability)
            if score.score_status == "OK" and label in (0, 1):
                p, _ = prior_prediction(bundle.unconditional_prior, row, regimes.get(identifier))
                if p is not None:
                    classification["unconditional_prior"][0].append(int(label))
                    classification["unconditional_prior"][1].append(float(p))
                p, _ = prior_prediction(bundle.regime_prior, row, regimes.get(identifier))
                if p is not None:
                    classification["regime_prior"][0].append(int(label))
                    classification["regime_prior"][1].append(float(p))
                sim = similarities.get(identifier)
                if sim is not None:
                    sim_p = sim.historical_win_probability if isinstance(sim, SimilarityResult) else sim.get("historical_win_probability")
                    if sim_p is not None:
                        classification["historical_similarity"][0].append(int(label))
                        classification["historical_similarity"][1].append(float(sim_p))
            if score.score_status == "OK" and expected is not None:
                if bundle.ridge is not None:
                    prediction = bundle.ridge.predict(vector)
                    regression["ridge_regression"][0].append(float(expected))
                    regression["ridge_regression"][1].append(prediction)
                    breakdown_records.append(({**row, "__score_confidence": score.model_confidence}, float(expected), prediction))
                p, expected_prior = prior_prediction(bundle.unconditional_prior, row, regimes.get(identifier))
                if expected_prior is not None:
                    regression["unconditional_prior"][0].append(float(expected))
                    regression["unconditional_prior"][1].append(float(expected_prior))
                _, expected_prior = prior_prediction(bundle.regime_prior, row, regimes.get(identifier))
                if expected_prior is not None:
                    regression["regime_prior"][0].append(float(expected))
                    regression["regime_prior"][1].append(float(expected_prior))
                sim = similarities.get(identifier)
                if sim is not None:
                    sim_r = sim.historical_expected_r if isinstance(sim, SimilarityResult) else sim.get("historical_expected_r")
                    if sim_r is not None:
                        regression["historical_similarity"][0].append(float(expected))
                        regression["historical_similarity"][1].append(float(sim_r))
            all_prediction_rows.append({"split": split, **score.to_dict()})
        by_split[split] = {
            "count": len(evaluation_rows),
            "classification": {model: _classification_payload(values[0], values[1]) for model, values in sorted(classification.items())},
            "regression": {model: regression_metrics(values[0], values[1]) for model, values in sorted(regression.items())},
            "regression_breakdown": {
                "regime": _grouped_regression(breakdown_records, lambda row: _regime_name(regimes.get(str(row.get("canonical_opportunity_id"))))),
                "side": _grouped_regression(breakdown_records, lambda row: row.get("side", "UNKNOWN")),
                "timeframe": _grouped_regression(breakdown_records, lambda row: row.get("timeframe", "UNKNOWN")),
                "calendar_period": _grouped_regression(breakdown_records, lambda row: str(row.get("timestamp_utc", "UNKNOWN"))[:7]),
                "confidence_bucket": _grouped_regression(breakdown_records, lambda row: row.get("__score_confidence", "UNKNOWN")),
            },
            "diagnostic_target_coverage": {
                target: {
                    "count": len(diagnostic_targets.get(target, [])),
                    "mean_realized_r": (
                        sum(diagnostic_targets[target]) / len(diagnostic_targets[target])
                        if diagnostic_targets.get(target) else None
                    ),
                }
                for target in DIAGNOSTIC_TARGETS
            },
        }
    bundle_config = bundle.metadata.get("config") if isinstance(bundle.metadata, Mapping) else None
    walk_config = ModelConfig.from_dict(bundle_config) if isinstance(bundle_config, Mapping) else ModelConfig()
    walk_forward = walk_forward_evaluate(records, splits, config=walk_config, regimes=regimes)
    edge_status = predictive_edge_status(by_split, walk_forward)
    return {
        "schema": "trading_agent_phase2_model_validation_v1",
        "model_version": bundle.model_version,
        "feature_version": bundle.feature_set_version,
        "fit_scope": "TRAIN_ONLY",
        "calibration_scope": "TRAIN_VALIDATION_ONLY",
        "oos_used_for_tuning": False,
        "by_split": by_split,
        "walk_forward": walk_forward,
        "predictive_edge_status": edge_status,
        "predictions": all_prediction_rows,
    }


def _regime_name(value: Any) -> str:
    if hasattr(value, "composite_regime"):
        return str(value.composite_regime)
    if isinstance(value, Mapping):
        return str(value.get("composite_regime", "UNKNOWN"))
    return str(value or "UNKNOWN")


def predictive_edge_status(by_split: Mapping[str, Any], walk_forward: Mapping[str, Any]) -> str:
    """Fixed, pre-declared conservative classification of predictive edge."""

    oos = by_split.get("OOS", {}).get("classification", {})
    logistic = oos.get("logistic_regression", {})
    prior = oos.get("unconditional_prior", {})
    count = int(logistic.get("count", 0) or 0)
    if count < 20 or logistic.get("brier_score") is None or prior.get("brier_score") is None:
        return "INSUFFICIENT_DATA"
    improvement = float(prior["brier_score"]) - float(logistic["brier_score"])
    auc = logistic.get("roc_auc")
    wf = walk_forward.get("aggregate", {})
    wf_improvement = wf.get("brier_improvement")
    if not isinstance(wf_improvement, (int, float)):
        return "INSUFFICIENT_DATA"
    if improvement >= 0.01 and isinstance(auc, (int, float)) and auc >= 0.55 and wf_improvement > 0:
        return "DEMONSTRATED"
    if (improvement >= 0.005 or (isinstance(auc, (int, float)) and auc >= 0.52)) and wf_improvement >= 0:
        return "WEAK"
    return "NOT_DEMONSTRATED"


def walk_forward_evaluate(
    rows: Iterable[Mapping[str, Any]],
    splits: Mapping[str, str],
    *,
    config: ModelConfig | None = None,
    regimes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expanding windows with a strict training_end < evaluation_start gate."""

    config = config or ModelConfig()
    records = sorted(rows, key=lambda row: (str(row.get("timestamp_utc", "")), str(row.get("canonical_opportunity_id", ""))))
    identifiers = [str(row.get("canonical_opportunity_id") or "") for row in records]
    if any(not identifier for identifier in identifiers):
        raise ValueError("walk-forward input requires canonical_opportunity_id")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("walk-forward input contains duplicate canonical samples")
    regimes = regimes or {}
    folds: list[dict[str, Any]] = []
    for evaluation_split in ("VALIDATION", "OOS"):
        evaluation_rows = _split_records(records, evaluation_split, splits)
        if not evaluation_rows:
            continue
        evaluation_start = min(timestamp_to_datetime(str(row["timestamp_utc"])) for row in evaluation_rows)
        training_rows = [
            row for row in records
            if splits.get(str(row.get("canonical_opportunity_id"))) in {"TRAIN", "VALIDATION"}
            and str(row.get("feature_status", "")).upper() != "CONFLICT"
            and timestamp_to_datetime(str(row["timestamp_utc"])) < evaluation_start
            and (evaluation_split == "OOS" or splits.get(str(row.get("canonical_opportunity_id"))) == "TRAIN")
        ]
        training_ids = [str(row["canonical_opportunity_id"]) for row in training_rows]
        preprocessor = TrainOnlyPreprocessor.fit(training_rows, training_ids, training_cutoff=max((str(row["timestamp_utc"]) for row in training_rows), default=None)) if training_rows else TrainOnlyPreprocessor.fit([], [])
        train_vectors = preprocessor.transform(training_rows)
        eval_vectors = preprocessor.transform(evaluation_rows)
        train_label_ids = [identifier for identifier in training_ids if build_label(next(row for row in training_rows if str(row["canonical_opportunity_id"]) == identifier)) in (0, 1)]
        train_regression_ids = [identifier for identifier in training_ids if build_expected_r_label(next(row for row in training_rows if str(row["canonical_opportunity_id"]) == identifier)) is not None]
        classification_labels: list[int] = []
        classification_predictions: list[float] = []
        prior_labels: list[int] = []
        prior_predictions: list[float] = []
        regression_realized: list[float] = []
        regression_predictions: list[float] = []
        logistic = None
        ridge = None
        training_label_values = [
            int(build_label(next(row for row in training_rows if str(row["canonical_opportunity_id"]) == identifier)))
            for identifier in train_label_ids
        ]
        prior_probability = sum(training_label_values) / len(training_label_values) if training_label_values else None
        if len(train_label_ids) >= config.min_training_labels:
            logistic = fit_logistic_regression(
                [train_vectors[item] for item in train_label_ids],
                [int(build_label(next(row for row in training_rows if str(row["canonical_opportunity_id"]) == item))) for item in train_label_ids],
                feature_names=preprocessor.output_names,
                fit_ids=train_label_ids,
                l2=config.logistic_l2,
                iterations=config.logistic_iterations,
                learning_rate=config.logistic_learning_rate,
            )
        if train_regression_ids:
            ridge = fit_ridge_regression(
                [train_vectors[item] for item in train_regression_ids],
                [float(build_expected_r_label(next(row for row in training_rows if str(row["canonical_opportunity_id"]) == item))) for item in train_regression_ids],
                feature_names=preprocessor.output_names,
                fit_ids=train_regression_ids,
                l2=config.ridge_l2,
            )
        abstention_count = 0
        for row in evaluation_rows:
            identifier = str(row["canonical_opportunity_id"])
            if (
                str(row.get("feature_status", "")).upper() == "CONFLICT"
                or preprocessor.ood_check(row)["is_ood"]
                or preprocessor.feature_completeness(row) < 0.25
            ):
                abstention_count += 1
                continue
            label = build_label(row)
            if logistic is not None and label in (0, 1):
                classification_labels.append(int(label))
                classification_predictions.append(logistic.predict_proba(eval_vectors[identifier]))
            if prior_probability is not None and label in (0, 1):
                prior_labels.append(int(label))
                prior_predictions.append(prior_probability)
            actual = build_expected_r_label(row)
            if ridge is not None and actual is not None:
                regression_realized.append(float(actual))
                regression_predictions.append(ridge.predict(eval_vectors[identifier]))
        classification = {
            "logistic_regression": _classification_payload(classification_labels, classification_predictions),
            "unconditional_prior": _classification_payload(prior_labels, prior_predictions),
        }
        regression = regression_metrics(regression_realized, regression_predictions)
        folds.append({
            "evaluation_split": evaluation_split,
            "training_start": min((str(row["timestamp_utc"]) for row in training_rows), default=None),
            "training_end": max((str(row["timestamp_utc"]) for row in training_rows), default=None),
            "evaluation_start": min((str(row["timestamp_utc"]) for row in evaluation_rows), default=None),
            "evaluation_end": max((str(row["timestamp_utc"]) for row in evaluation_rows), default=None),
            "training_count": len(training_rows),
            "evaluation_count": len(evaluation_rows),
            "evaluated_count": len(evaluation_rows) - abstention_count,
            "abstention_count": abstention_count,
            "classification": classification,
            "regression": regression,
            "temporal_guard": bool(not training_rows or max(timestamp_to_datetime(str(row["timestamp_utc"])) for row in training_rows) < evaluation_start),
            "oos_used_for_fit": False,
        })
    improvements = []
    for fold in folds:
        model_brier = fold["classification"].get("logistic_regression", {}).get("brier_score")
        prior_brier = fold["classification"].get("unconditional_prior", {}).get("brier_score")
        if model_brier is not None and prior_brier is not None:
            improvements.append(float(prior_brier) - float(model_brier))
    aggregate = {
        "brier_improvement": sum(improvements) / len(improvements) if improvements else None,
        "folds_with_comparison": len(improvements),
    }
    # The aggregate compares each fold's model with its own prior.  It never
    # selects a configuration based on the OOS fold.
    return {"schema": "trading_agent_phase2_walk_forward_v1", "folds": folds, "aggregate": aggregate, "config": config.to_dict()}


__all__ = ["evaluate_models", "predictive_edge_status", "regression_metrics", "walk_forward_evaluate"]
