"""Hàm dùng chung cho các parser CSV MT5."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..normalization.numbers import normalize_scalar


INTEGER_FIELDS = {
    "year", "setup_generation", "active_base_position_identifier", "active_pyramid_adds",
    "active_bars_open", "active_position_count", "age_bars", "repeat_bars",
}
BOOLEAN_FIELDS = {
    "long_valid", "short_valid", "low_efficiency", "high_spread_r", "high_volatility",
    "hit_1r", "hit_minus_1r",
    "completed", "shadow_build_valid", "active_is_be", "active_tp1_done", "active_tp2_done",
    "active_runner_active", "active_plus_1r_hit", "active_minus_1r_hit", "shadow_plus_1r_hit",
    "shadow_minus_1r_hit", "shadow_plus_1r_first", "shadow_minus_1r_first",
    "actual_selected_build_valid", "actual_selected_plus_1r_hit", "actual_selected_minus_1r_hit",
    "actual_selected_plus_1r_first", "actual_selected_minus_1r_first",
}


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError(f"CSV không có header: {path}")
        rows = list(reader)
    return rows, fieldnames


def normalize_fields(row: Mapping[str, str]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field, value in row.items():
        if field is None:
            continue
        kind = "boolean" if field in BOOLEAN_FIELDS else ("integer" if field in INTEGER_FIELDS else "number" if _looks_numeric(field) else "text")
        fields[field] = normalize_scalar(value, field=field, kind=kind)
    return fields


def _looks_numeric(field: str) -> bool:
    if field in {
        "active_side", "shadow_side", "active_first_hit", "shadow_first_hit",
        "actual_selected_first_hit", "shadow_build_reason", "incomplete_reason",
        "event_type", "direction", "conflict_type", "live_position_state",
        "live_position_side", "setup_id", "active_group_id", "symbol", "timeframe",
        "fold", "side", "blocked_side", "actual_selected_side", "d1_bias", "h4_bias",
        "h1_bias", "long_reject", "short_reject", "raw_event_type",
        "event_time", "entry_bar_time", "entry_time", "exit_time", "time",
    }:
        return False
    prefixes = (
        "d1_regime", "h4_regime", "composite_regime", "entry_", "shadow_", "active_",
        "actual_selected_", "opportunity_diff_", "return_", "mfe_", "mae_", "price_",
        "rsi_", "atr", "initial_sl", "risk_distance", "entry_price", "stop_loss",
        "take_profit", "mfe", "mae", "forward_return", "hit_",
    )
    return field.startswith(prefixes) and field not in {"active_side", "shadow_side", "active_first_hit"}


def as_text(fields: Mapping[str, Any], key: str, default: str | None = None) -> str | None:
    value = fields.get(key)
    if value is None:
        return default
    return str(value).strip() or default
