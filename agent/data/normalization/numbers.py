"""Numeric/boolean parsing fail-closed cho CSV MT5."""

from __future__ import annotations

import math


class NumericNormalizationError(ValueError):
    """Giá trị số không thể dùng an toàn."""


BOOLEAN_TOKENS = {
    "true": True,
    "false": False,
    "1": True,
    "0": False,
    "yes": True,
    "no": False,
}


def parse_number(value: object, *, field: str, integer: bool = False) -> int | float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError) as exc:
        raise NumericNormalizationError(f"{field}: numeric không hợp lệ {raw!r}") from exc
    if not math.isfinite(number):
        raise NumericNormalizationError(f"{field}: NaN/Infinity không được phép")
    if integer:
        if not number.is_integer():
            raise NumericNormalizationError(f"{field}: yêu cầu integer, nhận {raw!r}")
        return int(number)
    return number


def parse_bool(value: object, *, field: str, allow_empty: bool = True) -> bool | None:
    raw = str(value or "").strip().lower()
    if not raw and allow_empty:
        return None
    if raw not in BOOLEAN_TOKENS:
        raise NumericNormalizationError(f"{field}: boolean không hợp lệ {raw!r}")
    return BOOLEAN_TOKENS[raw]


def normalize_scalar(value: object, *, field: str, kind: str = "text") -> object:
    if kind == "number":
        return parse_number(value, field=field)
    if kind == "integer":
        return parse_number(value, field=field, integer=True)
    if kind == "boolean":
        return parse_bool(value, field=field)
    raw = str(value or "").strip()
    return raw or None
