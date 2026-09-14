"""Auditable rule-based Regime Engine V1."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..features.registry import extract_feature_fields
from .config import RegimeConfig
from .models import RegimeAssignment


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip().upper()
    return text or None


def _fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return extract_feature_fields(row)


def _source_trend(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    if text in {"TRENDING", "TREND", "BULL", "BULLISH", "BEAR", "BEARISH", "UP", "DOWN"}:
        return "TRENDING"
    if text in {"MEAN_REVERTING", "MEAN-REVERTING", "MEAN_REVERSION", "REVERTING"}:
        return "MEAN_REVERTING"
    if text in {"NEUTRAL", "RANGE", "RANGING", "FLAT"}:
        return "NEUTRAL"
    return None


class RegimeEngine:
    def __init__(self, config: RegimeConfig):
        self.config = config

    def assign(self, row: Mapping[str, Any]) -> RegimeAssignment:
        fields = _fields(row)
        identifier = str(row.get("canonical_opportunity_id", ""))
        thresholds = self.config.thresholds
        reasons: list[str] = []

        trend = _source_trend(fields.get("source_regime"))
        if trend is None:
            score = _number(fields.get("composite_regime_score"))
            score_threshold = _number(thresholds.get("trend_score_threshold"))
            if score is not None and score_threshold is not None:
                if score >= score_threshold:
                    trend = "TRENDING"
                elif score <= -score_threshold:
                    trend = "MEAN_REVERTING"
                else:
                    trend = "NEUTRAL"
            else:
                z = _number(fields.get("price_z20"))
                z_threshold = _number(thresholds.get("trend_abs_z_threshold"))
                if z is not None and z_threshold is not None:
                    trend = "MEAN_REVERTING" if abs(z) >= z_threshold else "NEUTRAL"
                else:
                    biases = [_source_trend(fields.get(name)) for name in ("d1_bias", "h4_bias", "h1_bias")]
                    known_biases = [item for item in biases if item is not None]
                    if known_biases and len(set(known_biases)) == 1:
                        trend = known_biases[0]
        if trend is None:
            trend = "UNKNOWN"
            reasons.append("insufficient_trend_features")

        volatility_value = _number(fields.get("atr_percent"))
        volatility_source = "atr_percent"
        if volatility_value is None:
            volatility_value = _number(fields.get("return_std_20"))
            volatility_source = "return_std_20"
        if volatility_source == "atr_percent":
            low = _number(thresholds.get("atr_volatility_low", thresholds.get("volatility_low")))
            high = _number(thresholds.get("atr_volatility_high", thresholds.get("volatility_high")))
        else:
            low = _number(thresholds.get("std_volatility_low", thresholds.get("volatility_low")))
            high = _number(thresholds.get("std_volatility_high", thresholds.get("volatility_high")))
        if volatility_value is None or low is None or high is None:
            volatility = "UNKNOWN"
            reasons.append("insufficient_volatility_features")
        elif volatility_value < low:
            volatility = "LOW"
        elif volatility_value >= high:
            volatility = "HIGH"
        else:
            volatility = "NORMAL"

        spread = _number(fields.get("spread_r"))
        stressed_threshold = _number(thresholds.get("liquidity_spread_stressed"))
        if spread is None or stressed_threshold is None:
            liquidity = "UNKNOWN"
            reasons.append("insufficient_liquidity_features")
        else:
            liquidity = "STRESSED" if spread >= stressed_threshold else "NORMAL"

        if trend == "UNKNOWN" or volatility == "UNKNOWN":
            composite = "UNKNOWN"
        else:
            prefix = "TREND" if trend == "TRENDING" else "RANGE"
            composite = f"{prefix}_{volatility}_VOL"
        known_dimensions = sum(value != "UNKNOWN" for value in (trend, volatility, liquidity))
        confidence = "HIGH" if known_dimensions == 3 else "MEDIUM" if known_dimensions == 2 else "LOW"
        if not reasons:
            reasons.append("all_regime_dimensions_available")
        return RegimeAssignment(
            canonical_opportunity_id=identifier,
            trend_state=trend,
            volatility_state=volatility,
            liquidity_state=liquidity,
            composite_regime=composite,
            confidence=confidence,
            reason=";".join(reasons),
            source_reported_regime=_text(fields.get("source_regime")),
            regime_version=self.config.version,
        )

    def assign_many(self, rows: Iterable[Mapping[str, Any]]) -> dict[str, RegimeAssignment]:
        return {
            item.canonical_opportunity_id: item
            for item in (self.assign(row) for row in rows)
        }


def assign_regime(row: Mapping[str, Any], config: RegimeConfig) -> RegimeAssignment:
    return RegimeEngine(config).assign(row)


__all__ = ["RegimeAssignment", "RegimeEngine", "assign_regime"]
