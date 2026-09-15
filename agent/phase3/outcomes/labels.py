"""Các phép tính label/outcome thuần, không sửa prediction."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from ..models import parse_utc_timestamp


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def directional_return(side: str, price: Any, entry_price: float, risk_distance: float) -> float | None:
    """Tính return theo R với cùng chiều semantics của Phase 2."""

    value = _number(price)
    if value is None or risk_distance <= 0:
        return None
    sign = 1.0 if str(side).upper() == "LONG" else -1.0
    return sign * (value - entry_price) / risk_distance


def _bar_timestamp(bar: Mapping[str, Any]) -> Any:
    value = bar.get("timestamp_utc", bar.get("timestamp"))
    if not value:
        raise ValueError("future bar requires timestamp_utc")
    return parse_utc_timestamp(str(value))


def first_hit_label(
    side: str,
    bars: Iterable[Mapping[str, Any]],
    *,
    entry_price: float,
    risk_distance: float,
) -> tuple[int | None, str | None, str | None]:
    """Trả (label, first_hit, reason), với cùng-bar hai phía là ambiguous."""

    if risk_distance <= 0:
        return None, None, "INVALID_RISK_DISTANCE"
    is_long = str(side).upper() == "LONG"
    plus_level = entry_price + risk_distance if is_long else entry_price - risk_distance
    minus_level = entry_price - risk_distance if is_long else entry_price + risk_distance
    ordered = sorted(bars, key=lambda item: (_bar_timestamp(item), str(item.get("bar_id", ""))))
    for bar in ordered:
        high = _number(bar.get("high"))
        low = _number(bar.get("low"))
        close = _number(bar.get("close"))
        if high is None and low is None and close is None:
            continue
        high = high if high is not None else close
        low = low if low is not None else close
        plus_hit = high >= plus_level if is_long else low <= plus_level
        minus_hit = low <= minus_level if is_long else high >= minus_level
        if plus_hit and minus_hit:
            return None, "AMBIGUOUS", "AMBIGUOUS_SAME_BAR"
        if plus_hit:
            return 1, "PLUS_1R", None
        if minus_hit:
            return 0, "MINUS_1R", None
    return None, None, "NO_FIRST_HIT"


__all__ = ["directional_return", "first_hit_label"]
