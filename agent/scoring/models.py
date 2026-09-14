"""Dependency-light deterministic baseline model implementations."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence


def _sigmoid(value: float) -> float:
    if value >= 0:
        exponent = math.exp(-min(value, 700.0))
        return 1.0 / (1.0 + exponent)
    exponent = math.exp(max(value, -700.0))
    return exponent / (1.0 + exponent)


def _logit(probability: float) -> float:
    probability = min(max(probability, 1e-9), 1.0 - 1e-9)
    return math.log(probability / (1.0 - probability))


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Deterministic Gaussian elimination with partial pivoting."""

    size = len(vector)
    augmented = [list(matrix[index]) + [vector[index]] for index in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: (abs(augmented[row][column]), -row))
        if abs(augmented[pivot][column]) < 1e-12:
            augmented[pivot][column] = 1e-12
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for item in range(column, size + 1):
            augmented[column][item] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for item in range(column, size + 1):
                augmented[row][item] -= factor * augmented[column][item]
    return [augmented[index][-1] for index in range(size)]


@dataclass(frozen=True)
class LogisticRegressionModel:
    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    l2: float
    iterations: int
    learning_rate: float
    fit_ids: tuple[str, ...]
    model_version: str = "logistic-regression/1"
    constant_probability: float | None = None

    def predict_logit(self, vector: Sequence[float]) -> float:
        if self.constant_probability is not None:
            return _logit(self.constant_probability)
        return self.intercept + sum(coefficient * float(value) for coefficient, value in zip(self.coefficients, vector))

    def predict_proba(self, vector: Sequence[float]) -> float:
        return _sigmoid(self.predict_logit(vector))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"feature_names": list(self.feature_names), "fit_ids": list(self.fit_ids)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LogisticRegressionModel":
        return cls(
            feature_names=tuple(payload.get("feature_names", ())),
            coefficients=tuple(float(value) for value in payload.get("coefficients", ())),
            intercept=float(payload.get("intercept", 0.0)),
            l2=float(payload.get("l2", 1.0)),
            iterations=int(payload.get("iterations", 0)),
            learning_rate=float(payload.get("learning_rate", 0.05)),
            fit_ids=tuple(str(value) for value in payload.get("fit_ids", ())),
            model_version=str(payload.get("model_version", "logistic-regression/1")),
            constant_probability=payload.get("constant_probability"),
        )


def fit_logistic_regression(
    matrix: Sequence[Sequence[float]],
    labels: Sequence[int],
    *,
    feature_names: Sequence[str] = (),
    fit_ids: Iterable[str] = (),
    l2: float = 1.0,
    iterations: int = 400,
    learning_rate: float = 0.05,
) -> LogisticRegressionModel:
    if not matrix or not labels or len(matrix) != len(labels):
        raise ValueError("logistic regression requires non-empty aligned training data")
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise ValueError("logistic matrix rows have inconsistent widths")
    unique = sorted(set(int(value) for value in labels))
    fit_ids_tuple = tuple(sorted(str(value) for value in fit_ids))
    if len(unique) == 1:
        return LogisticRegressionModel(
            feature_names=tuple(feature_names), coefficients=tuple(0.0 for _ in range(width)),
            intercept=_logit(float(unique[0])), l2=l2, iterations=0, learning_rate=learning_rate,
            fit_ids=fit_ids_tuple, constant_probability=float(unique[0]),
        )
    probability = min(max(sum(labels) / len(labels), 1e-6), 1.0 - 1e-6)
    intercept = _logit(probability)
    coefficients = [0.0] * width
    for _ in range(iterations):
        gradient_intercept = 0.0
        gradient = [0.0] * width
        for row, target in zip(matrix, labels):
            estimate = _sigmoid(intercept + sum(coefficient * value for coefficient, value in zip(coefficients, row)))
            error = estimate - int(target)
            gradient_intercept += error
            for index, value in enumerate(row):
                gradient[index] += error * value
        scale = 1.0 / len(labels)
        intercept -= learning_rate * gradient_intercept * scale
        for index in range(width):
            coefficients[index] -= learning_rate * (gradient[index] * scale + l2 * coefficients[index])
    return LogisticRegressionModel(
        feature_names=tuple(feature_names), coefficients=tuple(coefficients), intercept=intercept,
        l2=l2, iterations=iterations, learning_rate=learning_rate, fit_ids=fit_ids_tuple,
    )


@dataclass(frozen=True)
class RidgeRegressionModel:
    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    l2: float
    fit_ids: tuple[str, ...]
    model_version: str = "ridge-regression/1"

    def predict(self, vector: Sequence[float]) -> float:
        return self.intercept + sum(coefficient * float(value) for coefficient, value in zip(self.coefficients, vector))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"feature_names": list(self.feature_names), "fit_ids": list(self.fit_ids)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RidgeRegressionModel":
        return cls(
            feature_names=tuple(payload.get("feature_names", ())),
            coefficients=tuple(float(value) for value in payload.get("coefficients", ())),
            intercept=float(payload.get("intercept", 0.0)),
            l2=float(payload.get("l2", 1.0)),
            fit_ids=tuple(str(value) for value in payload.get("fit_ids", ())),
            model_version=str(payload.get("model_version", "ridge-regression/1")),
        )


def fit_ridge_regression(
    matrix: Sequence[Sequence[float]],
    targets: Sequence[float],
    *,
    feature_names: Sequence[str] = (),
    fit_ids: Iterable[str] = (),
    l2: float = 1.0,
) -> RidgeRegressionModel:
    if not matrix or not targets or len(matrix) != len(targets):
        raise ValueError("ridge regression requires non-empty aligned training data")
    width = len(matrix[0])
    size = width + 1
    normal = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size
    for row, target in zip(matrix, targets):
        augmented = [1.0] + [float(value) for value in row]
        for left in range(size):
            rhs[left] += augmented[left] * float(target)
            for right in range(size):
                normal[left][right] += augmented[left] * augmented[right]
    for index in range(1, size):
        normal[index][index] += l2
    solution = _solve(normal, rhs)
    return RidgeRegressionModel(
        feature_names=tuple(feature_names), coefficients=tuple(solution[1:]), intercept=solution[0],
        l2=l2, fit_ids=tuple(sorted(str(value) for value in fit_ids)),
    )


@dataclass(frozen=True)
class PriorModel:
    model_type: str
    probability: float | None
    expected_r: float | None
    support: int
    expected_support: int
    fit_ids: tuple[str, ...] = ()
    by_group: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["fit_ids"] = list(self.fit_ids)
        value["by_group"] = {key: dict(item) for key, item in sorted(self.by_group.items())}
        return value

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PriorModel":
        return cls(
            model_type=str(payload.get("model_type", "prior")),
            probability=payload.get("probability"),
            expected_r=payload.get("expected_r"),
            support=int(payload.get("support", 0)),
            expected_support=int(payload.get("expected_support", 0)),
            fit_ids=tuple(str(value) for value in payload.get("fit_ids", ())),
            by_group=dict(payload.get("by_group", {})),
        )


__all__ = [
    "LogisticRegressionModel",
    "PriorModel",
    "RidgeRegressionModel",
    "fit_logistic_regression",
    "fit_ridge_regression",
]
