"""Train-only imputation, scaling and deterministic categorical encoding."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from .fingerprint import fingerprint
from .registry import (
    CATEGORICAL_FEATURES,
    CONTEXT_FEATURES,
    FEATURE_SET_VERSION,
    NUMERIC_FEATURES,
    extract_feature_fields,
)


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    value = str(value).strip()
    return value.upper() if value else None


@dataclass(frozen=True)
class TrainOnlyPreprocessor:
    """Serializable preprocessing state fitted exclusively on TRAIN rows."""

    feature_set_version: str = FEATURE_SET_VERSION
    numeric_features: tuple[str, ...] = NUMERIC_FEATURES
    categorical_features: tuple[str, ...] = CATEGORICAL_FEATURES + CONTEXT_FEATURES
    imputation: str = "mean"
    numeric_stats: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    categorical_levels: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    output_names: tuple[str, ...] = ()
    fit_ids: tuple[str, ...] = ()
    training_cutoff: str | None = None
    ood_z_limit: float = 4.0

    @classmethod
    def fit(
        cls,
        rows: Iterable[Mapping[str, Any]],
        train_ids: Iterable[str],
        *,
        imputation: str = "mean",
        training_cutoff: str | None = None,
        ood_z_limit: float = 4.0,
    ) -> "TrainOnlyPreprocessor":
        all_rows = list(rows)
        wanted = tuple(sorted({str(item) for item in train_ids}))
        by_id = {str(row.get("canonical_opportunity_id")): row for row in all_rows}
        if len(by_id) != len(all_rows):
            raise ValueError("preprocessor input contains duplicate canonical samples")
        missing_ids = [item for item in wanted if item not in by_id]
        if missing_ids:
            raise ValueError(f"TRAIN ids missing from canonical rows: {missing_ids[:3]}")
        train_rows = [by_id[item] for item in wanted]

        numeric_stats: dict[str, dict[str, Any]] = {}
        for name in NUMERIC_FEATURES:
            values = []
            for row in train_rows:
                value = _number(extract_feature_fields(row).get(name))
                if value is not None:
                    values.append(value)
            if values:
                mean = sum(values) / len(values)
                med = float(median(values))
                variance = sum((value - mean) ** 2 for value in values) / len(values)
                std = math.sqrt(variance)
                if std <= 1e-15:
                    std = 1.0
            else:
                # This fallback is not a magic missing value: all-missing is
                # explicitly represented by the indicator in the output.
                mean = 0.0
                med = 0.0
                std = 1.0
            numeric_stats[name] = {
                "count": len(values),
                "mean": mean,
                "median": med,
                "std": std,
                "all_missing": not bool(values),
                "fit_scope": "TRAIN_ONLY",
            }

        # Context fields are categorical features too.  Fit their vocabulary
        # from TRAIN, just like identity fields, so a source-reported bias or
        # regime can contribute to the vector when it is available without
        # allowing validation/OOS categories to expand the schema.
        categorical_features = CATEGORICAL_FEATURES + CONTEXT_FEATURES
        categorical_levels: dict[str, tuple[str, ...]] = {}
        for name in categorical_features:
            levels = sorted(
                {
                    value
                    for row in train_rows
                    if (value := _text(extract_feature_fields(row).get(name))) is not None
                }
            )
            categorical_levels[name] = tuple(levels)

        output_names: list[str] = []
        for name in NUMERIC_FEATURES:
            output_names.extend((name, f"{name}__missing"))
        for name in categorical_features:
            output_names.extend(f"{name}={level}" for level in categorical_levels[name])
            output_names.append(f"{name}__missing")
        return cls(
            numeric_stats=numeric_stats,
            categorical_levels=categorical_levels,
            output_names=tuple(output_names),
            fit_ids=wanted,
            training_cutoff=training_cutoff,
            imputation=imputation,
            ood_z_limit=ood_z_limit,
        )

    def transform_one(self, row: Mapping[str, Any]) -> tuple[float, ...]:
        fields = extract_feature_fields(row)
        values: list[float] = []
        for name in self.numeric_features:
            raw = _number(fields.get(name))
            missing = raw is None
            stats = self.numeric_stats.get(name, {"mean": 0.0, "std": 1.0})
            impute_value = float(stats.get("median" if self.imputation == "median" else "mean", 0.0))
            number = impute_value if missing else raw
            std = float(stats.get("std", 1.0)) or 1.0
            mean = float(stats.get("mean", 0.0))
            values.append((number - mean) / std)
            values.append(1.0 if missing else 0.0)
        for name in self.categorical_features:
            value = _text(fields.get(name))
            levels = self.categorical_levels.get(name, ())
            values.extend(1.0 if value == level else 0.0 for level in levels)
            values.append(1.0 if value is None or value not in levels else 0.0)
        return tuple(values)

    def transform(self, rows: Iterable[Mapping[str, Any]]) -> dict[str, tuple[float, ...]]:
        records = list(rows)
        identifiers = [str(row["canonical_opportunity_id"]) for row in records]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("preprocessor transform input contains duplicate canonical samples")
        return {identifier: self.transform_one(row) for identifier, row in zip(identifiers, records)}

    def feature_completeness(self, row: Mapping[str, Any]) -> float:
        fields = extract_feature_fields(row)
        all_names = tuple(self.numeric_features) + tuple(self.categorical_features)
        if not all_names:
            return 0.0
        return sum(_number(fields.get(name)) is not None if name in self.numeric_features else _text(fields.get(name)) is not None for name in all_names) / len(all_names)

    def ood_reasons(self, row: Mapping[str, Any]) -> list[str]:
        fields = extract_feature_fields(row)
        reasons: list[str] = []
        if not self.fit_ids:
            return ["NO_TRAIN_SUPPORT"]
        for name in self.numeric_features:
            value = _number(fields.get(name))
            if value is None:
                continue
            stats = self.numeric_stats.get(name)
            if not stats or int(stats.get("count", 0)) == 0:
                reasons.append(f"{name}:unseen_training_distribution")
                continue
            z = abs((value - float(stats["mean"])) / (float(stats["std"]) or 1.0))
            if z > self.ood_z_limit:
                reasons.append(f"{name}:z={z:.4f}>{self.ood_z_limit:g}")
        for name in self.categorical_features:
            value = _text(fields.get(name))
            if value is not None and value not in self.categorical_levels.get(name, ()):
                reasons.append(f"{name}:unseen_category={value}")
        return reasons

    def ood_check(self, row: Mapping[str, Any]) -> dict[str, Any]:
        reasons = self.ood_reasons(row)
        return {"is_ood": bool(reasons), "reasons": reasons, "z_limit": self.ood_z_limit}

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_set_version": self.feature_set_version,
            "numeric_features": list(self.numeric_features),
            "categorical_features": list(self.categorical_features),
            "imputation": self.imputation,
            "numeric_stats": {key: dict(value) for key, value in sorted(self.numeric_stats.items())},
            "categorical_levels": {key: list(value) for key, value in sorted(self.categorical_levels.items())},
            "output_names": list(self.output_names),
            "fit_ids": list(self.fit_ids),
            "training_cutoff": self.training_cutoff,
            "ood_z_limit": self.ood_z_limit,
            "preprocessing_fingerprint": fingerprint({
                "numeric_stats": self.numeric_stats,
                "categorical_levels": self.categorical_levels,
                "output_names": self.output_names,
                "fit_ids": self.fit_ids,
            }),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TrainOnlyPreprocessor":
        return cls(
            feature_set_version=str(payload.get("feature_set_version", FEATURE_SET_VERSION)),
            numeric_features=tuple(payload.get("numeric_features", NUMERIC_FEATURES)),
            categorical_features=tuple(payload.get("categorical_features", CATEGORICAL_FEATURES + CONTEXT_FEATURES)),
            imputation=str(payload.get("imputation", "mean")),
            numeric_stats={str(key): dict(value) for key, value in dict(payload.get("numeric_stats", {})).items()},
            categorical_levels={str(key): tuple(value) for key, value in dict(payload.get("categorical_levels", {})).items()},
            output_names=tuple(payload.get("output_names", ())),
            fit_ids=tuple(str(value) for value in payload.get("fit_ids", ())),
            training_cutoff=payload.get("training_cutoff"),
            ood_z_limit=float(payload.get("ood_z_limit", 4.0)),
        )


def fit_train_only_preprocessor(*args: Any, **kwargs: Any) -> TrainOnlyPreprocessor:
    return TrainOnlyPreprocessor.fit(*args, **kwargs)


__all__ = ["TrainOnlyPreprocessor", "fit_train_only_preprocessor"]
