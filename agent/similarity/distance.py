"""Feature-only standardized Euclidean distance."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Iterable

from ..features.registry import FeatureLeakageError, FeatureSchemaError, is_outcome_field, validate_feature_columns


def _validate_vector_names(names: Iterable[str]) -> None:
    direct: list[str] = []
    for name in names:
        name = str(name)
        if is_outcome_field(name):
            raise FeatureLeakageError(f"outcome field rejected from similarity distance: {name}")
        if name.endswith("__missing"):
            base = name[:-9]
            if not base:
                raise FeatureSchemaError(f"invalid normalized feature name: {name}")
            direct.append(base)
        elif "=" in name:
            base = name.split("=", 1)[0]
            direct.append(base)
        else:
            direct.append(name)
    validate_feature_columns(direct)


def _pairs(left: Any, right: Any, feature_names: Sequence[str] | None) -> list[tuple[Any, Any]]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        _validate_vector_names(set(left) | set(right))
        names = list(feature_names) if feature_names is not None else sorted(set(left) & set(right))
        return [(left.get(name), right.get(name)) for name in names]
    if not isinstance(left, Sequence) or isinstance(left, (str, bytes)) or not isinstance(right, Sequence) or isinstance(right, (str, bytes)):
        raise TypeError("distance inputs must be mappings or numeric sequences")
    if len(left) != len(right):
        raise ValueError("distance vectors must have equal length")
    if feature_names is not None and len(feature_names) != len(left):
        raise ValueError("feature_names length does not match vector length")
    if feature_names is not None:
        _validate_vector_names(feature_names)
    return list(zip(left, right))


def distance_with_overlap(
    left: Mapping[str, Any] | Sequence[Any],
    right: Mapping[str, Any] | Sequence[Any],
    *,
    feature_names: Sequence[str] | None = None,
    min_overlap: int = 1,
) -> tuple[float | None, int]:
    pairs = _pairs(left, right, feature_names)
    squared = 0.0
    overlap = 0
    for first, second in pairs:
        if first is None or second is None:
            continue
        try:
            first_number, second_number = float(first), float(second)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(first_number) or not math.isfinite(second_number):
            continue
        squared += (first_number - second_number) ** 2
        overlap += 1
    if overlap < min_overlap:
        return None, overlap
    return math.sqrt(squared / overlap), overlap


def standardized_euclidean(
    left: Mapping[str, Any] | Sequence[Any],
    right: Mapping[str, Any] | Sequence[Any],
    *,
    feature_names: Sequence[str] | None = None,
    min_overlap: int = 1,
) -> float | None:
    return distance_with_overlap(left, right, feature_names=feature_names, min_overlap=min_overlap)[0]


__all__ = ["distance_with_overlap", "standardized_euclidean"]
