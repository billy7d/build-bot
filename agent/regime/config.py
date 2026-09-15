"""Regime thresholds with explicit TRAIN-only estimation provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from ..features.registry import extract_feature_fields


def _numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


@dataclass(frozen=True)
class RegimeConfig:
    version: str = "regime/1"
    threshold_source: str = "TRAIN_DISTRIBUTION_AND_STRATEGY_SEMANTICS"
    training_cutoff: str | None = None
    training_ids: tuple[str, ...] = ()
    thresholds: Mapping[str, Any] = field(default_factory=dict)
    taxonomy: Mapping[str, Any] = field(default_factory=lambda: {
        "trend_state": ["TRENDING", "NEUTRAL", "MEAN_REVERTING", "UNKNOWN"],
        "volatility_state": ["LOW", "NORMAL", "HIGH", "UNKNOWN"],
        "liquidity_state": ["NORMAL", "STRESSED", "UNKNOWN"],
        "composite": ["TREND_HIGH_VOL", "TREND_NORMAL_VOL", "TREND_LOW_VOL", "RANGE_HIGH_VOL", "RANGE_NORMAL_VOL", "RANGE_LOW_VOL", "UNKNOWN"],
    })

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["training_ids"] = list(self.training_ids)
        value["thresholds"] = {key: self.thresholds[key] for key in sorted(self.thresholds)}
        return value

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RegimeConfig":
        return cls(
            version=str(payload.get("version", "regime/1")),
            threshold_source=str(payload.get("threshold_source", "TRAIN_DISTRIBUTION_AND_STRATEGY_SEMANTICS")),
            training_cutoff=payload.get("training_cutoff"),
            training_ids=tuple(str(item) for item in payload.get("training_ids", ())),
            thresholds=dict(payload.get("thresholds", {})),
            taxonomy=dict(payload.get("taxonomy", {})) or cls().taxonomy,
        )


def fit_regime_config(
    rows: Iterable[Mapping[str, Any]],
    train_ids: Iterable[str],
    *,
    version: str = "regime/1",
    training_cutoff: str | None = None,
    trend_score_threshold: float = 0.5,
) -> RegimeConfig:
    """Derive all distribution thresholds from TRAIN rows only."""

    records = {str(row.get("canonical_opportunity_id")): row for row in rows}
    ids = tuple(sorted({str(item) for item in train_ids}))
    usable_ids = tuple(
        item for item in ids
        if item in records and str(records[item].get("feature_status", "")).upper() != "CONFLICT"
    )
    train_rows = [
        records[item] for item in usable_ids
    ]
    atr = []
    std = []
    spread = []
    abs_z = []
    for row in train_rows:
        fields = extract_feature_fields(row)
        if (value := _numeric(fields.get("atr_percent"))) is not None:
            atr.append(value)
        if (value := _numeric(fields.get("return_std_20"))) is not None:
            std.append(value)
        if (value := _numeric(fields.get("spread_r"))) is not None:
            spread.append(value)
        if (value := _numeric(fields.get("price_abs_z20"))) is not None:
            abs_z.append(value)
        elif (value := _numeric(fields.get("price_z20"))) is not None:
            abs_z.append(abs(value))
    vol_values = atr or std
    thresholds = {
        "volatility_source_feature": "atr_percent" if atr else "return_std_20" if std else None,
        "volatility_low": _quantile(vol_values, 1 / 3),
        "volatility_high": _quantile(vol_values, 2 / 3),
        # Keep a second train-only distribution so a missing ATR can fall
        # back to StdDev (and vice versa) without borrowing a validation/OOS
        # threshold.
        "atr_volatility_low": _quantile(atr, 1 / 3),
        "atr_volatility_high": _quantile(atr, 2 / 3),
        "std_volatility_low": _quantile(std, 1 / 3),
        "std_volatility_high": _quantile(std, 2 / 3),
        "liquidity_spread_stressed": _quantile(spread, 0.95),
        "trend_score_threshold": float(trend_score_threshold),
        "trend_abs_z_threshold": _quantile(abs_z, 0.75) if abs_z else None,
        "volatility_training_count": len(vol_values),
        "spread_training_count": len(spread),
        "trend_training_count": len(abs_z),
        "threshold_fit_scope": "TRAIN_ONLY",
    }
    return RegimeConfig(
        version=version,
        training_cutoff=training_cutoff,
        training_ids=usable_ids,
        thresholds=thresholds,
    )


__all__ = ["RegimeConfig", "fit_regime_config"]
