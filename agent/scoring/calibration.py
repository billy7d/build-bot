"""Classification calibration and evaluation metrics."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from .models import _logit, _sigmoid


def _clip(value: float) -> float:
    return min(max(float(value), 1e-15), 1.0 - 1e-15)


def brier_score(labels: Sequence[int], probabilities: Sequence[float]) -> float | None:
    if not labels or len(labels) != len(probabilities):
        return None
    return sum((_clip(probability) - int(label)) ** 2 for label, probability in zip(labels, probabilities)) / len(labels)


def log_loss(labels: Sequence[int], probabilities: Sequence[float]) -> float | None:
    if not labels or len(labels) != len(probabilities):
        return None
    return -sum(int(label) * math.log(_clip(probability)) + (1 - int(label)) * math.log(1.0 - _clip(probability)) for label, probability in zip(labels, probabilities)) / len(labels)


def _rank_auc(labels: Sequence[int], probabilities: Sequence[float]) -> float | None:
    positives = sum(int(label) for label in labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    order = sorted(range(len(labels)), key=lambda index: (float(probabilities[index]), index))
    rank_sum = 0.0
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and float(probabilities[order[end]]) == float(probabilities[order[index]]):
            end += 1
        average_rank = (index + 1 + end) / 2.0
        rank_sum += sum(average_rank for item in order[index:end] if int(labels[item]) == 1)
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def roc_auc(labels: Sequence[int], probabilities: Sequence[float]) -> float | None:
    return _rank_auc(labels, probabilities)


def pr_auc(labels: Sequence[int], probabilities: Sequence[float]) -> float | None:
    positives = sum(int(label) for label in labels)
    if not labels or positives == 0:
        return None
    order = sorted(range(len(labels)), key=lambda index: (-float(probabilities[index]), index))
    true_positive = 0
    previous_recall = 0.0
    area = 0.0
    for rank, index in enumerate(order, start=1):
        true_positive += int(labels[index])
        recall = true_positive / positives
        precision = true_positive / rank
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def calibration_bins(labels: Sequence[int], probabilities: Sequence[float], bins: int = 10) -> list[dict[str, Any]]:
    grouped: list[list[tuple[int, float]]] = [[] for _ in range(max(1, bins))]
    for label, probability in zip(labels, probabilities):
        index = min(max(int(float(probability) * bins), 0), bins - 1)
        grouped[index].append((int(label), float(probability)))
    result = []
    for index, values in enumerate(grouped):
        result.append({
            "bin": index,
            "lower": index / bins,
            "upper": (index + 1) / bins,
            "count": len(values),
            "mean_predicted": sum(value for _, value in values) / len(values) if values else None,
            "mean_realized": sum(label for label, _ in values) / len(values) if values else None,
        })
    return result


def expected_calibration_error(labels: Sequence[int], probabilities: Sequence[float], bins: int = 10) -> float | None:
    if not labels or len(labels) != len(probabilities):
        return None
    return sum(
        item["count"] / len(labels) * abs(item["mean_predicted"] - item["mean_realized"])
        for item in calibration_bins(labels, probabilities, bins)
        if item["count"]
    )


@dataclass(frozen=True)
class PlattCalibrator:
    slope: float = 1.0
    intercept: float = 0.0
    fit_ids: tuple[str, ...] = ()
    fit_scope: str = "TRAIN_VALIDATION"
    model_version: str = "platt/1"

    def transform(self, probability: float) -> float:
        return _sigmoid(self.slope * _logit(float(probability)) + self.intercept)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["fit_ids"] = list(self.fit_ids)
        return value

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlattCalibrator":
        return cls(
            slope=float(payload.get("slope", 1.0)), intercept=float(payload.get("intercept", 0.0)),
            fit_ids=tuple(str(value) for value in payload.get("fit_ids", ())),
            fit_scope=str(payload.get("fit_scope", "TRAIN_VALIDATION")),
            model_version=str(payload.get("model_version", "platt/1")),
        )


def fit_platt_calibrator(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    fit_ids: Iterable[str] = (),
    iterations: int = 250,
    learning_rate: float = 0.03,
) -> PlattCalibrator:
    if not probabilities or len(probabilities) != len(labels):
        return PlattCalibrator(fit_ids=tuple(sorted(str(value) for value in fit_ids)))
    slope, intercept = 1.0, 0.0
    logits = [_logit(_clip(value)) for value in probabilities]
    for _ in range(iterations):
        gradient_slope = 0.0
        gradient_intercept = 0.0
        for logit, label in zip(logits, labels):
            estimate = _sigmoid(slope * logit + intercept)
            error = estimate - int(label)
            gradient_slope += error * logit
            gradient_intercept += error
        scale = 1.0 / len(labels)
        slope -= learning_rate * gradient_slope * scale
        intercept -= learning_rate * gradient_intercept * scale
    return PlattCalibrator(slope, intercept, tuple(sorted(str(value) for value in fit_ids)))


def classification_metrics(labels: Sequence[int], probabilities: Sequence[float], *, bins: int = 10) -> dict[str, Any]:
    return {
        "count": len(labels),
        "brier_score": brier_score(labels, probabilities),
        "log_loss": log_loss(labels, probabilities),
        "roc_auc": roc_auc(labels, probabilities),
        "pr_auc": pr_auc(labels, probabilities),
        "calibration_bins": calibration_bins(labels, probabilities, bins),
        "expected_calibration_error": expected_calibration_error(labels, probabilities, bins),
    }


__all__ = [
    "PlattCalibrator",
    "brier_score",
    "calibration_bins",
    "classification_metrics",
    "expected_calibration_error",
    "fit_platt_calibrator",
    "log_loss",
    "pr_auc",
    "roc_auc",
]
