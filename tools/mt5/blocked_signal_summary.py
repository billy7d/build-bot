#!/usr/bin/env python3
"""Tổng hợp V82 blocked-signal/opportunity-cost audit bằng Python chuẩn.

CSV V82 được ghi một lần khi event hoàn tất 48 nến hoặc khi tester kết thúc.
Các event chưa đủ cửa sổ forward vẫn được giữ trong inventory nhưng không đi
vào các metric kết quả.  Script này không tạo execution conclusion; nó chỉ
đánh giá discovery/promotion gates đã đăng ký trước trong PRD.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence


HORIZONS = (6, 12, 24, 48)
REQUIRED_FIELDS = {
    "event_id",
    "event_time",
    "entry_bar_time",
    "year",
    "fold",
    "side",
    "event_type",
    "active_side",
    "shadow_side",
    "actual_selected_side",
    "blocked_side",
    "direction",
    "setup_generation",
    "active_group_id",
    "active_base_position_identifier",
    "shadow_build_valid",
    "shadow_build_reason",
    "long_reject",
    "short_reject",
    "shadow_entry_price",
    "shadow_spread",
    "shadow_initial_sl",
    "actual_selected_build_valid",
    "shadow_risk_distance",
    "shadow_entry_rsi",
    "shadow_entry_rsi_ema",
    "shadow_entry_rsi_wma",
    "d1_bias",
    "h4_bias",
    "h1_bias",
    "d1_regime_score",
    "h4_regime_score",
    "composite_regime_score",
    "entry_atr_pct",
    "entry_atr_rank",
    "entry_efficiency_20",
    "entry_spread_r",
    "initial_sl_atr",
    "active_entry_price",
    "active_current_price",
    "active_initial_risk",
    "active_initial_risk_distance",
    "active_current_r",
    "active_sl",
    "active_is_be",
    "active_tp1_done",
    "active_tp2_done",
    "active_runner_active",
    "active_pyramid_adds",
    "active_bars_open",
    "active_locked_profit_r",
    "active_group_volume",
    "active_position_count",
    "active_value_at_event_r",
    *(f"active_value_{bars}bar_r" for bars in HORIZONS),
    "shadow_first_hit",
    "shadow_mfe_r",
    "shadow_mae_r",
    *(f"shadow_return_{bars}bar_r" for bars in HORIZONS),
    *(f"active_continuation_{bars}bar_r" for bars in HORIZONS),
    *(f"opportunity_diff_{bars}bar_r" for bars in HORIZONS),
    *(f"actual_selected_return_{bars}bar_r" for bars in HORIZONS),
    "active_plus_1r_hit",
    "active_minus_1r_hit",
    "active_first_hit",
    "shadow_plus_1r_hit",
    "shadow_minus_1r_hit",
    "shadow_plus_1r_first",
    "shadow_minus_1r_first",
    "actual_selected_entry_price",
    "actual_selected_initial_sl",
    "actual_selected_risk_distance",
    "actual_selected_plus_1r_hit",
    "actual_selected_minus_1r_hit",
    "actual_selected_plus_1r_first",
    "actual_selected_minus_1r_first",
    "actual_selected_first_hit",
    "actual_selected_mfe_r",
    "actual_selected_mae_r",
    "age_bars",
    "completed",
    "incomplete_reason",
}
NUMERIC_FIELDS = (
    "setup_generation",
    "active_base_position_identifier",
    "shadow_entry_price",
    "shadow_spread",
    "shadow_initial_sl",
    "shadow_risk_distance",
    "shadow_entry_rsi",
    "shadow_entry_rsi_ema",
    "shadow_entry_rsi_wma",
    "d1_regime_score",
    "h4_regime_score",
    "composite_regime_score",
    "entry_atr_pct",
    "entry_atr_rank",
    "entry_efficiency_20",
    "entry_spread_r",
    "initial_sl_atr",
    "active_entry_price",
    "active_current_price",
    "active_initial_risk",
    "active_initial_risk_distance",
    "active_current_r",
    "active_sl",
    "active_pyramid_adds",
    "active_bars_open",
    "active_locked_profit_r",
    "active_group_volume",
    "active_position_count",
    "active_value_at_event_r",
    *(f"active_value_{bars}bar_r" for bars in HORIZONS),
    *(f"active_continuation_{bars}bar_r" for bars in HORIZONS),
    "shadow_mfe_r",
    "shadow_mae_r",
    *(f"shadow_return_{bars}bar_r" for bars in HORIZONS),
    "actual_selected_entry_price",
    "actual_selected_initial_sl",
    "actual_selected_risk_distance",
    "actual_selected_mfe_r",
    "actual_selected_mae_r",
    *(f"actual_selected_return_{bars}bar_r" for bars in HORIZONS),
    *(f"opportunity_diff_{bars}bar_r" for bars in HORIZONS),
    "age_bars",
)
SIDE_VALUES = {"LONG", "SHORT", "NONE"}
EVENT_TYPES = {
    "BLOCKED_OPPOSITE",
    "BLOCKED_SAME_SIDE",
    "SIMULTANEOUS_CONFLICT",
    "LONG_ONLY",
    "SHORT_ONLY",
}
ACTIVE_EVENT_TYPES = {"BLOCKED_OPPOSITE", "BLOCKED_SAME_SIDE"}
BOOLEAN_FIELDS = (
    "shadow_build_valid",
    "actual_selected_build_valid",
    "active_is_be",
    "active_tp1_done",
    "active_tp2_done",
    "active_runner_active",
    "active_plus_1r_hit",
    "active_minus_1r_hit",
    "shadow_plus_1r_hit",
    "shadow_minus_1r_hit",
    "shadow_plus_1r_first",
    "shadow_minus_1r_first",
    "actual_selected_plus_1r_hit",
    "actual_selected_minus_1r_hit",
    "actual_selected_plus_1r_first",
    "actual_selected_minus_1r_first",
    "completed",
)
BOOLEAN_TOKENS = {"true", "false", "1", "0", "yes", "no"}
COMMON_COMPLETED_NUMERIC_FIELDS = (
    "shadow_risk_distance",
    "shadow_mfe_r",
    "shadow_mae_r",
    *(f"shadow_return_{bars}bar_r" for bars in HORIZONS),
)
ACTIVE_COMPLETED_NUMERIC_FIELDS = (
    "active_entry_price",
    "active_current_price",
    "active_initial_risk",
    "active_initial_risk_distance",
    "active_current_r",
    "active_sl",
    "active_pyramid_adds",
    "active_bars_open",
    "active_locked_profit_r",
    "active_group_volume",
    "active_position_count",
    "active_value_at_event_r",
    *(f"active_value_{bars}bar_r" for bars in HORIZONS),
    *(f"active_continuation_{bars}bar_r" for bars in HORIZONS),
    *(f"opportunity_diff_{bars}bar_r" for bars in HORIZONS),
)
CONFLICT_COMPLETED_NUMERIC_FIELDS = (
    "actual_selected_entry_price",
    "actual_selected_initial_sl",
    "actual_selected_risk_distance",
    "actual_selected_mfe_r",
    "actual_selected_mae_r",
    *(f"actual_selected_return_{bars}bar_r" for bars in HORIZONS),
)


def as_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def is_boolean_token(value: object) -> bool:
    """Kiểm tra boolean CSV thay vì âm thầm coi giá trị lạ là false."""
    return str(value or "").strip().lower() in BOOLEAN_TOKENS


def as_float(value: object) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def parse_time(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in (
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def year_segment(value: object) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return "unknown"
    if parsed.year == 2026:
        return "2026_H1" if parsed.month <= 6 else "2026_H2"
    return str(parsed.year)


def fold_for_year_segment(segment: str) -> str:
    if segment in {"2023", "2024"}:
        return "validation_2023_2024"
    if segment == "2025" or segment.startswith("2026_"):
        return "oos_2025_plus"
    return "other"


def canonical_direction(row: Mapping[str, object]) -> str:
    event_type = str(row.get("event_type") or "").strip().upper()
    active = str(row.get("active_side") or "NONE").strip().upper()
    shadow = str(row.get("shadow_side") or row.get("side") or "").strip().upper()
    selected = str(row.get("actual_selected_side") or "NONE").strip().upper()
    if event_type in ACTIVE_EVENT_TYPES:
        return f"{active} active -> {shadow} blocked"
    if event_type == "SIMULTANEOUS_CONFLICT":
        return f"FLAT -> {selected} selected / {shadow} blocked"
    if event_type == "LONG_ONLY":
        return "FLAT -> LONG control"
    if event_type == "SHORT_ONLY":
        return "FLAT -> SHORT control"
    return str(row.get("direction") or "UNKNOWN").strip() or "UNKNOWN"


def parse_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Đọc CSV MT5 bằng csv.DictReader, không cần dependency ngoài."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        return list(reader), list(reader.fieldnames or [])


def _field_values(rows: Iterable[Mapping[str, object]], field: str) -> list[float]:
    values = []
    for row in rows:
        value = as_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def _first_hit_metrics(rows: Sequence[Mapping[str, object]], prefix: str) -> dict[str, object]:
    first_field = f"{prefix}first_hit"
    plus = sum(str(row.get(first_field) or "").strip().upper() == "PLUS_1R" for row in rows)
    minus = sum(str(row.get(first_field) or "").strip().upper() == "MINUS_1R" for row in rows)
    resolved = plus + minus
    return {
        f"{prefix}plus1r_first": plus,
        f"{prefix}minus1r_first": minus,
        f"{prefix}resolved_events": resolved,
        f"{prefix}plus1r_first_rate": plus / resolved if resolved else None,
    }


def event_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Tính metrics cho một population đã lọc tới completed + valid events."""
    result: dict[str, object] = {
        "events": len(rows),
        "complete_events": len(rows),
    }
    result.update(_first_hit_metrics(rows, "shadow_"))
    result.update(_first_hit_metrics(rows, "active_"))
    result.update(_first_hit_metrics(rows, "actual_selected_"))

    for prefix, field_prefix in (
        ("shadow_return", "shadow_return"),
        ("active_continuation", "active_continuation"),
        ("opportunity_diff", "opportunity_diff"),
    ):
        for bars in HORIZONS:
            field = f"{field_prefix}_{bars}bar_r"
            values = _field_values(rows, field)
            result[f"mean_{prefix}_{bars}_r"] = mean(values)
            result[f"median_{prefix}_{bars}_r"] = median(values)

    for prefix, field_prefix in (
        ("shadow", "shadow"),
        ("active", "active"),
        ("actual_selected", "actual_selected"),
    ):
        for name in ("mfe_r", "mae_r"):
            result[f"median_{prefix}_{name}"] = median(_field_values(rows, f"{field_prefix}_{name}"))
    return result


def _empty_quality() -> dict[str, object]:
    return {
        "rows": 0,
        "schema_missing_fields": [],
        "missing_event_id_rows": 0,
        "duplicate_event_ids": 0,
        "duplicate_event_id_values": [],
        "nan_or_inf_values": 0,
        "nan_or_inf_by_field": {},
        "invalid_numeric_values": 0,
        "invalid_numeric_by_field": {},
        "invalid_side_rows": 0,
        "invalid_event_type_rows": 0,
        "invalid_event_relation_rows": 0,
        "invalid_boolean_values": 0,
        "invalid_time_rows": 0,
        "negative_risk_distance_rows": 0,
        "zero_or_missing_risk_rows": 0,
        "negative_age_rows": 0,
        "completed_before_horizon_rows": 0,
        "horizon_lookahead_rows": 0,
        "missing_completed_outcome_rows": 0,
        "missing_completed_outcome_by_field": {},
        # CSV không quan sát được việc ghi MQL global; giá trị 0 này đi kèm
        # hợp đồng cô lập ở source và regression execution OFF/ON.
        "state_mutation_violations": 0,
        "valid_completed_events": 0,
        "incomplete_valid_events": 0,
        "invalid_build_events": 0,
        "quality_gate_pass": False,
    }


def _validate_rows(rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str], expected_forward_bars: int) -> tuple[dict[str, object], list[dict[str, object]]]:
    quality = _empty_quality()
    quality["rows"] = len(rows)
    missing = sorted(REQUIRED_FIELDS - set(fieldnames))
    quality["schema_missing_fields"] = missing

    ids = Counter(str(row.get("event_id") or "").strip() for row in rows if str(row.get("event_id") or "").strip())
    duplicate_ids = sorted(event_id for event_id, count in ids.items() if count > 1)
    quality["duplicate_event_ids"] = sum(ids[event_id] - 1 for event_id in duplicate_ids)
    quality["duplicate_event_id_values"] = duplicate_ids

    nonfinite_by_field: Counter[str] = Counter()
    invalid_numeric_by_field: Counter[str] = Counter()
    valid_complete: list[dict[str, object]] = []
    incomplete_valid = 0
    invalid_build = 0
    missing_completed_outcome_by_field: Counter[str] = Counter()

    for row_number, original in enumerate(rows, start=2):
        row = dict(original)
        row["__row_number"] = row_number
        row["__year_segment"] = year_segment(row.get("event_time"))
        row["__fold"] = fold_for_year_segment(row["__year_segment"])
        row["__direction"] = canonical_direction(row)
        row["__event_type"] = str(row.get("event_type") or "").strip().upper()
        row["__side"] = str(row.get("side") or "").strip().upper()

        if not str(row.get("event_id") or "").strip():
            quality["missing_event_id_rows"] += 1

        for field in BOOLEAN_FIELDS:
            if not is_boolean_token(row.get(field)):
                quality["invalid_boolean_values"] += 1

        for field in NUMERIC_FIELDS:
            if field not in row:
                continue
            raw = str(row.get(field) or "").strip()
            if not raw:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                invalid_numeric_by_field[field] += 1
                continue
            if not math.isfinite(value):
                nonfinite_by_field[field] += 1
                continue
            row[f"__number_{field}"] = value

        side = row["__side"]
        active_side = str(row.get("active_side") or "NONE").strip().upper()
        shadow_side = str(row.get("shadow_side") or "").strip().upper()
        selected_side = str(row.get("actual_selected_side") or "NONE").strip().upper()
        event_type = row["__event_type"]
        if side not in {"LONG", "SHORT"} or active_side not in SIDE_VALUES or shadow_side not in {"LONG", "SHORT"} or selected_side not in SIDE_VALUES:
            quality["invalid_side_rows"] += 1
        if event_type not in EVENT_TYPES:
            quality["invalid_event_type_rows"] += 1
        relation_valid = True
        if event_type in ACTIVE_EVENT_TYPES:
            relation_valid = (
                active_side in {"LONG", "SHORT"}
                and shadow_side == side
                and selected_side == "NONE"
                and str(row.get("blocked_side") or "").strip().upper() == shadow_side
                and (
                    (event_type == "BLOCKED_OPPOSITE" and active_side != shadow_side)
                    or (event_type == "BLOCKED_SAME_SIDE" and active_side == shadow_side)
                )
            )
        elif event_type == "SIMULTANEOUS_CONFLICT":
            relation_valid = (
                active_side == "NONE"
                and shadow_side == side
                and selected_side == "LONG"
                and str(row.get("blocked_side") or "").strip().upper() == shadow_side
            )
        elif event_type in {"LONG_ONLY", "SHORT_ONLY"}:
            expected_side = "LONG" if event_type == "LONG_ONLY" else "SHORT"
            relation_valid = (
                active_side == "NONE"
                and side == expected_side
                and shadow_side == expected_side
                and selected_side == expected_side
                and str(row.get("blocked_side") or "").strip().upper() == "NONE"
            )
        if event_type in EVENT_TYPES and not relation_valid:
            quality["invalid_event_relation_rows"] += 1
        if parse_time(row.get("event_time")) is None or parse_time(row.get("entry_bar_time")) is None:
            quality["invalid_time_rows"] += 1

        risk = row.get("__number_shadow_risk_distance")
        if risk is None and as_bool(row.get("shadow_build_valid")):
            quality["zero_or_missing_risk_rows"] += 1
        elif risk is not None and risk < 0.0:
            quality["negative_risk_distance_rows"] += 1
        elif risk is not None and risk <= 0.0 and as_bool(row.get("shadow_build_valid")):
            quality["zero_or_missing_risk_rows"] += 1

        age = row.get("__number_age_bars")
        if age is not None and age < 0:
            quality["negative_age_rows"] += 1
        if as_bool(row.get("completed")) and (age is None or age < expected_forward_bars):
            quality["completed_before_horizon_rows"] += 1

        event_time = parse_time(row.get("event_time"))
        entry_time = parse_time(row.get("entry_bar_time"))
        if event_time is not None and entry_time is not None and entry_time > event_time:
            quality["horizon_lookahead_rows"] += 1

        horizon_field_prefixes = (
            "shadow_return",
            "active_continuation",
            "opportunity_diff",
            "actual_selected_return",
        )
        for bars in HORIZONS:
            for prefix in horizon_field_prefixes:
                field = f"{prefix}_{bars}bar_r"
                if row.get(f"__number_{field}") is not None and age is not None and age < bars:
                    quality["horizon_lookahead_rows"] += 1

        if not as_bool(row.get("shadow_build_valid")):
            invalid_build += 1
            continue
        if as_bool(row.get("completed")):
            required_outcomes = list(COMMON_COMPLETED_NUMERIC_FIELDS)
            if event_type in ACTIVE_EVENT_TYPES:
                required_outcomes.extend(ACTIVE_COMPLETED_NUMERIC_FIELDS)
            if event_type == "SIMULTANEOUS_CONFLICT":
                if not as_bool(row.get("actual_selected_build_valid")):
                    quality["missing_completed_outcome_rows"] += 1
                    missing_completed_outcome_by_field["actual_selected_build_valid"] += 1
                    continue
                required_outcomes.extend(CONFLICT_COMPLETED_NUMERIC_FIELDS)
            missing_outcomes = [field for field in required_outcomes if as_float(row.get(field)) is None]
            if missing_outcomes:
                quality["missing_completed_outcome_rows"] += 1
                for field in missing_outcomes:
                    missing_completed_outcome_by_field[field] += 1
                continue
            valid_complete.append(row)
        else:
            incomplete_valid += 1

    quality["nan_or_inf_values"] = sum(nonfinite_by_field.values())
    quality["nan_or_inf_by_field"] = dict(sorted(nonfinite_by_field.items()))
    quality["invalid_numeric_values"] = sum(invalid_numeric_by_field.values())
    quality["invalid_numeric_by_field"] = dict(sorted(invalid_numeric_by_field.items()))
    quality["missing_completed_outcome_by_field"] = dict(sorted(missing_completed_outcome_by_field.items()))
    quality["valid_completed_events"] = len(valid_complete)
    quality["incomplete_valid_events"] = incomplete_valid
    quality["invalid_build_events"] = invalid_build
    quality["quality_gate_pass"] = not any(
        quality[key]
        for key in (
            "schema_missing_fields",
            "missing_event_id_rows",
            "duplicate_event_ids",
            "nan_or_inf_values",
            "invalid_numeric_values",
            "invalid_side_rows",
            "invalid_event_type_rows",
            "invalid_event_relation_rows",
            "invalid_boolean_values",
            "invalid_time_rows",
            "negative_risk_distance_rows",
            "zero_or_missing_risk_rows",
            "negative_age_rows",
            "completed_before_horizon_rows",
            "horizon_lookahead_rows",
            "missing_completed_outcome_rows",
            "state_mutation_violations",
        )
    )
    return quality, valid_complete


def _group_metrics(rows: Sequence[Mapping[str, object]], keys: Sequence[str]) -> list[dict[str, object]]:
    groups: defaultdict[tuple[object, ...], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(key) for key in keys)].append(row)
    output = []
    for values, group_rows in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0])):
        item = {(key[2:] if key.startswith("__") else key): value for key, value in zip(keys, values)}
        item.update(event_metrics(group_rows))
        output.append(item)
    return output


def _maturity_bucket(row: Mapping[str, object]) -> str:
    current_r = row.get("__number_active_current_r")
    if current_r is None:
        return "unknown"
    if current_r < 0:
        return "active_r_lt_0"
    if current_r < 1:
        return "active_r_0_1"
    if current_r < 2:
        return "active_r_1_2"
    return "active_r_ge_2"


def _pyramid_bucket(row: Mapping[str, object]) -> str:
    adds = row.get("__number_active_pyramid_adds")
    if adds is None:
        return "unknown"
    return "before_add1" if adds < 1 else "after_add1"


def _opportunity_snapshot(rows: Sequence[Mapping[str, object]], bars: int) -> dict[str, object]:
    result = event_metrics(rows)
    return {
        "events": result["events"],
        "complete_events": result["complete_events"],
        "mean_opportunity_diff_r": result[f"mean_opportunity_diff_{bars}_r"],
        "median_opportunity_diff_r": result[f"median_opportunity_diff_{bars}_r"],
        "blocked_plus1r_first_rate": result["shadow_plus1r_first_rate"],
        "active_plus1r_first_rate": result["active_plus1r_first_rate"],
        "first_rate_difference": (
            result["shadow_plus1r_first_rate"] - result["active_plus1r_first_rate"]
            if result["shadow_plus1r_first_rate"] is not None and result["active_plus1r_first_rate"] is not None
            else None
        ),
    }


def _directional_hypothesis(rows: Sequence[Mapping[str, object]], name: str, event_type: str, active_side: str, shadow_side: str, expected_forward_bars: int) -> dict[str, object]:
    selected = [
        row
        for row in rows
        if row["__event_type"] == event_type
        and str(row.get("active_side") or "").strip().upper() == active_side
        and str(row.get("shadow_side") or "").strip().upper() == shadow_side
    ]
    folds = {}
    for fold in ("validation_2023_2024", "oos_2025_plus"):
        fold_rows = [row for row in selected if row.get("__fold") == fold]
        folds[fold] = {str(bars): _opportunity_snapshot(fold_rows, bars) for bars in (24, 48)}

    validation_24 = folds["validation_2023_2024"]["24"]["median_opportunity_diff_r"]
    oos_24 = folds["oos_2025_plus"]["24"]["median_opportunity_diff_r"]
    validation_48 = folds["validation_2023_2024"]["48"]["median_opportunity_diff_r"]
    oos_48 = folds["oos_2025_plus"]["48"]["median_opportunity_diff_r"]
    sample_gate = (
        folds["validation_2023_2024"]["24"]["complete_events"] >= 30
        and folds["oos_2025_plus"]["24"]["complete_events"] >= 30
    )
    direction_gate = (
        validation_24 is not None
        and oos_24 is not None
        and validation_24 > 0.0
        and oos_24 > 0.0
    )
    first_rate_diffs = [
        folds[fold]["48"]["first_rate_difference"]
        for fold in ("validation_2023_2024", "oos_2025_plus")
        if folds[fold]["48"]["first_rate_difference"] is not None
    ]
    materiality_gate = (
        (validation_48 is not None and validation_48 >= 0.20)
        or (oos_48 is not None and oos_48 >= 0.20)
        or any(value >= 0.08 for value in first_rate_diffs)
    )
    stability_gate = (
        validation_24 is not None
        and oos_24 is not None
        and ((validation_24 > 0 and oos_24 > 0) or (validation_24 < 0 and oos_24 < 0))
    )

    year_rows = defaultdict(list)
    for row in selected:
        year_rows[row.get("__year_segment", "unknown")].append(row)
    year_checks = []
    for year, year_group in sorted(year_rows.items()):
        if year in {"unknown", "other"}:
            continue
        metrics = event_metrics(year_group)
        diff = metrics["median_opportunity_diff_24_r"]
        year_checks.append(
            {
                "year": year,
                "complete_events": len(year_group),
                "median_opportunity_diff_24_r": diff,
                "eligible_for_concentration_check": len(year_group) >= 30,
                "positive": diff is not None and diff > 0.0,
            }
        )
    eligible_years = [item for item in year_checks if item["eligible_for_concentration_check"]]
    positive_years = sum(item["positive"] for item in eligible_years)
    if len(eligible_years) >= 3:
        year_concentration_status = positive_years >= 3
        year_concentration_reason = "at_least_three_of_three_or_more_eligible_year_segments_positive"
    else:
        year_concentration_status = False
        year_concentration_reason = "fewer_than_three_year_segments_have_30_completed_events"

    gates = {
        "sample": sample_gate,
        "direction": direction_gate,
        "materiality": materiality_gate,
        "stability": stability_gate,
        "year_concentration": year_concentration_status,
    }
    if all(gates.values()):
        conclusion = "PROMISING_FOR_EXECUTION_EXPERIMENT"
    elif not sample_gate:
        conclusion = "INSUFFICIENT_SAMPLE"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    return {
        "name": name,
        "event_type": event_type,
        "active_side": active_side,
        "shadow_side": shadow_side,
        "total_completed_events": len(selected),
        "folds": folds,
        "year_segments": year_checks,
        "sample_gate": {
            "minimum_validation_completed": 30,
            "minimum_oos_completed": 30,
            "validation_completed": folds["validation_2023_2024"]["24"]["complete_events"],
            "oos_completed": folds["oos_2025_plus"]["24"]["complete_events"],
            "passed": sample_gate,
        },
        "gates": gates,
        "year_concentration": {
            "eligible_year_segments": len(eligible_years),
            "positive_eligible_year_segments": positive_years,
            "passed": year_concentration_status,
            "reason": year_concentration_reason,
        },
        "promotion_eligible": all(gates.values()),
        "conclusion": conclusion,
        "threshold_mining": "not_performed",
    }


def _conflict_comparison(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    conflicts = [row for row in rows if row["__event_type"] == "SIMULTANEOUS_CONFLICT"]
    result: dict[str, object] = {"events": len(conflicts), "complete_events": len(conflicts)}
    for bars in HORIZONS:
        shadow = _field_values(conflicts, f"shadow_return_{bars}bar_r")
        actual = _field_values(conflicts, f"actual_selected_return_{bars}bar_r")
        result[f"mean_shadow_return_{bars}_r"] = mean(shadow)
        result[f"median_shadow_return_{bars}_r"] = median(shadow)
        result[f"mean_actual_selected_return_{bars}_r"] = mean(actual)
        result[f"median_actual_selected_return_{bars}_r"] = median(actual)
        differences = [
            shadow_value - actual_value
            for row in conflicts
            if (shadow_value := as_float(row.get(f"shadow_return_{bars}bar_r"))) is not None
            and (actual_value := as_float(row.get(f"actual_selected_return_{bars}bar_r"))) is not None
        ]
        result[f"mean_shadow_minus_actual_{bars}_r"] = mean(differences)
        result[f"median_shadow_minus_actual_{bars}_r"] = median(differences)
    result.update(_first_hit_metrics(conflicts, "shadow_"))
    result.update(_first_hit_metrics(conflicts, "actual_selected_"))
    return result


def build_summary(rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str] | None = None, expected_forward_bars: int = 48) -> dict[str, object]:
    """API kiểm thử chính; nhận rows DictReader hoặc list dict thông thường."""
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row.keys() if not str(key).startswith("__")})
    quality, valid_complete = _validate_rows(rows, fieldnames, expected_forward_bars)

    # _validate_rows đặt các key chuẩn hóa trên bản sao; thêm lại các key này
    # cho rows hoàn tất để nhóm metrics không phụ thuộc casing của CSV.
    for row in valid_complete:
        row["__active_side"] = str(row.get("active_side") or "NONE").strip().upper()
        row["__shadow_side"] = str(row.get("shadow_side") or row.get("side") or "").strip().upper()
        row["__event_type"] = str(row.get("event_type") or "").strip().upper()

    all_rows = [dict(row) for row in rows]
    inventory = Counter(str(row.get("event_type") or "UNKNOWN").strip().upper() for row in all_rows)
    inventory_complete = Counter(
        str(row.get("event_type") or "UNKNOWN").strip().upper()
        for row in valid_complete
    )

    fold_rows = []
    year_rows = []
    event_rows = []
    direction_rows = []
    maturity_rows = []
    pyramid_rows = []
    for row in valid_complete:
        row["__direction"] = canonical_direction(row)
        fold_rows.append(row)
        year_rows.append(row)
        event_rows.append(row)
        direction_rows.append(row)
        if row["__active_side"] != "NONE":
            maturity_rows.append(row)
            pyramid_rows.append(row)

    hypotheses = [
        _directional_hypothesis(valid_complete, "LONG active -> SHORT blocked", "BLOCKED_OPPOSITE", "LONG", "SHORT", expected_forward_bars),
        _directional_hypothesis(valid_complete, "SHORT active -> LONG blocked", "BLOCKED_OPPOSITE", "SHORT", "LONG", expected_forward_bars),
        _directional_hypothesis(valid_complete, "LONG active -> LONG blocked", "BLOCKED_SAME_SIDE", "LONG", "LONG", expected_forward_bars),
        _directional_hypothesis(valid_complete, "SHORT active -> SHORT blocked", "BLOCKED_SAME_SIDE", "SHORT", "SHORT", expected_forward_bars),
    ]

    return {
        "schema": "v82_blocked_signal_opportunity_audit_v1",
        "expected_forward_bars": expected_forward_bars,
        "input_rows": len(rows),
        "event_inventory": {
            "all_events_by_type": dict(sorted(inventory.items())),
            "completed_valid_events_by_type": dict(sorted(inventory_complete.items())),
            "incomplete_valid_events_excluded": quality["incomplete_valid_events"],
            "invalid_build_events_excluded": quality["invalid_build_events"],
        },
        "data_quality": quality,
        "fold_groups": _group_metrics(
            fold_rows,
            ("__fold", "__event_type", "__direction", "__active_side", "__shadow_side"),
        ),
        "year_groups": _group_metrics(
            year_rows,
            ("__year_segment", "__event_type", "__direction", "__active_side", "__shadow_side"),
        ),
        "event_type_groups": _group_metrics(event_rows, ("__event_type",)),
        "direction_groups": _group_metrics(direction_rows, ("__direction",)),
        "active_maturity_groups": _group_metrics_with_derived(maturity_rows, "__maturity", _maturity_bucket),
        "pyramid_groups": _group_metrics_with_derived(pyramid_rows, "__pyramid_state", _pyramid_bucket),
        "simultaneous_conflict": _conflict_comparison(valid_complete),
        "promotion_gates": hypotheses,
        "interpretation_policy": {
            "primary_horizons": [24, 48],
            "minimum_completed_validation_events": 30,
            "minimum_completed_oos_events": 30,
            "threshold_mining": "not_performed",
            "conclusion_scope": "audit_only; no execution change is authorized by this report",
        },
    }


def _group_metrics_with_derived(rows: Sequence[Mapping[str, object]], key: str, derive) -> list[dict[str, object]]:
    enriched = []
    for row in rows:
        copy = dict(row)
        copy[key] = derive(row)
        enriched.append(copy)
    return _group_metrics(enriched, (key,))


def _display(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "đạt" if value else "không đạt"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _markdown_table(rows: Sequence[Mapping[str, object]], columns: Sequence[tuple[str, str]]) -> str:
    if not rows:
        return "_(không có event phù hợp)_\n"
    header = "| " + " | ".join(label for _, label in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, separator]
    for row in rows:
        lines.append("| " + " | ".join(_display(row.get(key)) for key, _ in columns) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(summary: Mapping[str, object]) -> str:
    quality = summary["data_quality"]
    lines = [
        "# V82 Blocked Signal & Opportunity Cost Shadow Audit",
        "",
        "Báo cáo này chỉ phục vụ discovery/audit; không phải execution recommendation.",
        "",
        "## Chất lượng dữ liệu",
        "",
        _markdown_table(
            [
                {
                    "rows": quality["rows"],
                    "completed": quality["valid_completed_events"],
                    "incomplete": quality["incomplete_valid_events"],
                    "duplicates": quality["duplicate_event_ids"],
                    "nonfinite": quality["nan_or_inf_values"],
                    "invalid_risk": quality["negative_risk_distance_rows"],
                    "lookahead": quality["horizon_lookahead_rows"],
                    "pass": quality["quality_gate_pass"],
                }
            ],
            (
                ("rows", "rows"),
                ("completed", "completed hợp lệ"),
                ("incomplete", "incomplete"),
                ("duplicates", "duplicate ID"),
                ("nonfinite", "NaN/Inf"),
                ("invalid_risk", "risk âm"),
                ("lookahead", "lookahead"),
                ("pass", "quality gate"),
            ),
        ),
        "",
        "## Inventory",
        "",
        _markdown_table(
            [
                {"event_type": event_type, "events": count}
                for event_type, count in sorted(summary["event_inventory"]["all_events_by_type"].items())
            ],
            (("event_type", "event_type"), ("events", "events")),
        ),
        "## Fold / event type / direction",
        "",
        _markdown_table(
            summary["fold_groups"],
            (
                ("fold", "fold"),
                ("event_type", "event type"),
                ("direction", "direction"),
                ("complete_events", "complete"),
                ("shadow_plus1r_first_rate", "shadow +1R-first"),
                ("median_shadow_return_24_r", "shadow median 24R"),
                ("median_shadow_return_48_r", "shadow median 48R"),
                ("median_active_continuation_24_r", "active median cont. 24R"),
                ("median_active_continuation_48_r", "active median cont. 48R"),
                ("median_opportunity_diff_24_r", "median diff 24R"),
                ("median_opportunity_diff_48_r", "median diff 48R"),
            ),
        ),
        "## Year breakdown",
        "",
        _markdown_table(
            summary["year_groups"],
            (
                ("year_segment", "year"),
                ("event_type", "event type"),
                ("direction", "direction"),
                ("complete_events", "complete"),
                ("median_opportunity_diff_24_r", "median diff 24R"),
                ("median_opportunity_diff_48_r", "median diff 48R"),
            ),
        ),
        "## Active maturity / pyramid context",
        "",
        _markdown_table(
            summary["active_maturity_groups"],
            (("maturity", "active R bucket"), ("complete_events", "complete"), ("median_opportunity_diff_24_r", "median diff 24R"), ("median_opportunity_diff_48_r", "median diff 48R")),
        ),
        "",
        _markdown_table(
            summary["pyramid_groups"],
            (("pyramid_state", "pyramid state"), ("complete_events", "complete"), ("median_opportunity_diff_24_r", "median diff 24R"), ("median_opportunity_diff_48_r", "median diff 48R")),
        ),
        "## Simultaneous conflict",
        "",
        _markdown_table(
            [summary["simultaneous_conflict"]] if summary["simultaneous_conflict"]["events"] else [],
            (
                ("complete_events", "complete"),
                ("shadow_plus1r_first_rate", "shadow Short +1R-first"),
                ("actual_selected_plus1r_first_rate", "actual Long +1R-first"),
                ("median_shadow_minus_actual_24_r", "shadow−actual median 24R"),
                ("median_shadow_minus_actual_48_r", "shadow−actual median 48R"),
            ),
        ),
        "## Promotion gates",
        "",
        _markdown_table(
            [
                {
                    "name": hypothesis["name"],
                    "sample": hypothesis["gates"]["sample"],
                    "direction": hypothesis["gates"]["direction"],
                    "materiality": hypothesis["gates"]["materiality"],
                    "stability": hypothesis["gates"]["stability"],
                    "year": hypothesis["gates"]["year_concentration"],
                    "conclusion": hypothesis["conclusion"],
                }
                for hypothesis in summary["promotion_gates"]
            ],
            (
                ("name", "hypothesis"),
                ("sample", "sample"),
                ("direction", "direction"),
                ("materiality", "materiality"),
                ("stability", "stability"),
                ("year", "year concentration"),
                ("conclusion", "conclusion"),
            ),
        ),
        "",
        "Kết luận promotion chỉ có hiệu lực khi đủ sample Validation/OOS và qua toàn bộ gate; script không sửa EA và không bật gate execution.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", type=Path, nargs="+", help="Một hoặc nhiều CSV Mentor_RSI_MTF_v82_blocked_signals.csv")
    parser.add_argument("--output", "--json-output", dest="json_output", type=Path, help="Đường dẫn JSON đầu ra")
    parser.add_argument("--markdown-output", type=Path, help="Đường dẫn Markdown đầu ra")
    parser.add_argument("--expected-forward-bars", type=int, default=48)
    args = parser.parse_args()
    if args.expected_forward_bars < 48:
        parser.error("--expected-forward-bars phải >= 48")

    rows: list[dict[str, str]] = []
    fieldnames: set[str] = set()
    for path in args.csv_paths:
        parsed_rows, parsed_fields = parse_csv(path)
        rows.extend(parsed_rows)
        fieldnames.update(parsed_fields)
    summary = build_summary(rows, sorted(fieldnames), args.expected_forward_bars)
    encoded = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.json_output:
        args.json_output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    if args.markdown_output:
        args.markdown_output.write_text(render_markdown(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
