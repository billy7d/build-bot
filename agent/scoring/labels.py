"""Outcome-to-label conversion with explicit abstention semantics."""

from __future__ import annotations

import math
from typing import Any, Mapping


DIAGNOSTIC_TARGETS = (
    "shadow_return_6bar_r",
    "shadow_return_12bar_r",
    "shadow_return_48bar_r",
    "shadow_mfe_r",
    "shadow_mae_r",
)


def _labels(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("labels")
    return value if isinstance(value, Mapping) else row


def _bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def build_label(row: Mapping[str, Any]) -> int | None:
    """Return 1/0 only for an unambiguous completed first-hit outcome."""

    value = _labels(row)
    if value.get("incomplete_reason") not in (None, ""):
        return None
    if value.get("resolved") is not None and _bool(value.get("resolved")) is not True:
        return None
    first = str(value.get("shadow_first_hit") or value.get("first_hit") or "").strip().upper()
    plus = _bool(value.get("shadow_plus_1r_first"))
    minus = _bool(value.get("shadow_minus_1r_first"))
    plus_seen = value.get("shadow_plus_1r_first") not in (None, "")
    minus_seen = value.get("shadow_minus_1r_first") not in (None, "")
    canonical_label = value.get("plus_1r_before_minus_1r")
    if first in {"AMBIGUOUS", "UNRESOLVED", "INCOMPLETE", "NONE", ""} and plus is None and minus is None:
        return None
    if first == "AMBIGUOUS" or (plus is True and minus is True):
        return None
    if canonical_label in (0, 1):
        if (
            (canonical_label == 1 and (minus is True or (plus_seen and plus is not True)))
            or (canonical_label == 0 and (plus is True or (minus_seen and minus is not True)))
        ):
            return None
        return int(canonical_label)
    if first == "PLUS_1R" and ((plus_seen and plus is not True) or minus is True):
        return None
    if first == "MINUS_1R" and ((minus_seen and minus is not True) or plus is True):
        return None
    if first == "PLUS_1R" or plus is True:
        return 1 if minus is not True else None
    if first == "MINUS_1R" or minus is True:
        return 0 if plus is not True else None
    return None


def build_expected_r_label(row: Mapping[str, Any], horizon: int = 24) -> float | None:
    value = _labels(row)
    if value.get("incomplete_reason") not in (None, ""):
        return None
    if value.get("resolved") is not None and _bool(value.get("resolved")) is not True:
        return None
    result = _number(value.get(f"shadow_return_{horizon}bar_r"))
    if result is None and horizon == 24:
        result = _number(value.get("expected_r_24bar"))
    return result


def build_diagnostic_target(row: Mapping[str, Any], target: str) -> float | None:
    """Return a secondary realized-R diagnostic without changing the 24-bar target."""

    value = _labels(row)
    if target not in DIAGNOSTIC_TARGETS:
        raise ValueError(f"unknown diagnostic target: {target}")
    if value.get("incomplete_reason") not in (None, ""):
        return None
    if value.get("resolved") is not None and _bool(value.get("resolved")) is not True:
        return None
    return _number(value.get(target))


def build_label_record(row: Mapping[str, Any]) -> dict[str, Any]:
    value = _labels(row)
    return {
        "plus_1r_before_minus_1r": build_label(row),
        "expected_r_24bar": build_expected_r_label(row, 24),
        "expected_r_6bar": build_expected_r_label(row, 6),
        "expected_r_12bar": build_expected_r_label(row, 12),
        "expected_r_48bar": build_expected_r_label(row, 48),
        "mfe_r": _number(value.get("shadow_mfe_r")),
        "mae_r": _number(value.get("shadow_mae_r")),
        "label_status": "VALID" if build_label(row) is not None else "INSUFFICIENT",
        "incomplete_reason": value.get("incomplete_reason"),
        "resolved": value.get("resolved"),
        "outcome_timestamp_utc": value.get("outcome_timestamp_utc"),
    }


__all__ = ["DIAGNOSTIC_TARGETS", "build_diagnostic_target", "build_expected_r_label", "build_label", "build_label_record"]
