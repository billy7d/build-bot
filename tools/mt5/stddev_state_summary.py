#!/usr/bin/env python3
"""Tổng hợp audit Standard Deviation theo năm, fold, chiều và bucket cố định."""

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path


SHADOW_FIELDS = (
    "entry_return_std_20",
    "entry_return_std_rank",
    "entry_price_std_20",
    "entry_price_std_100",
    "entry_price_std_pct_20",
    "entry_std_ratio_20_100",
    "entry_price_z20",
    "entry_price_abs_z20",
    "entry_rsi_std_20",
    "entry_rsi_std_rank",
    "entry_atr_return_std_ratio",
    "entry_atr_return_std_rank",
)

PYRAMID_FIELDS = (
    "add_entry_price_z20",
    "add_entry_abs_z20",
    "add_return_std_rank",
    "add_atr_return_std_ratio",
    "add_atr_return_std_rank",
)

RETURN_FIELDS = ("return_6", "return_12", "return_24", "return_48")
NON_NEGATIVE_FIELDS = (
    "entry_return_std_20",
    "entry_price_std_20",
    "entry_price_std_100",
    "entry_price_std_pct_20",
    "entry_std_ratio_20_100",
    "entry_rsi_std_20",
    "entry_atr_return_std_ratio",
)
RANK_FIELDS = (
    "entry_return_std_rank",
    "entry_rsi_std_rank",
    "entry_atr_return_std_rank",
)

# Ngưỡng diễn giải được đăng ký trước; đây chỉ là cờ chất lượng mẫu, không phải execution gate.
MIN_EVENTS_FOR_INTERPRETATION = 30
MIN_RESOLVED_EVENTS_FOR_INTERPRETATION = 20


def parse_csv(path: Path):
    """Đọc CSV MT5 mà không cần dependency ngoài Python chuẩn."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def read_text_auto(path: Path):
    """Đọc journal UTF-16 của MT5 hoặc text UTF-8 mà không làm mất dòng chẩn đoán."""
    data = path.read_bytes()
    utf16_hint = data.startswith((b"\xff\xfe", b"\xfe\xff")) or data[:4096].count(b"\x00") > 8
    encoding = "utf-16" if utf16_hint else "utf-8"
    return data.decode(encoding, errors="replace")


def new_quality():
    return {
        "missing_values_by_field": Counter(),
        "invalid_numeric_by_field": Counter(),
        "nonfinite_values_by_field": Counter(),
        "negative_stddev_by_field": Counter(),
        "rank_out_of_range_by_field": Counter(),
        "negative_abs_z_events": 0,
        "schema_missing_fields": [],
    }


def numeric(row, field, quality):
    """Parse số hữu hạn; giá trị rỗng là missing, không biến thành zero."""
    cache_key = f"__stddev_numeric_{field}"
    if cache_key in row:
        return row[cache_key]

    if field not in row:
        quality["missing_values_by_field"][field] += 1
        row[cache_key] = None
        return None

    raw = (row.get(field) or "").strip()
    if not raw:
        quality["missing_values_by_field"][field] += 1
        row[cache_key] = None
        return None

    try:
        value = float(raw)
    except ValueError:
        quality["invalid_numeric_by_field"][field] += 1
        row[cache_key] = None
        return None

    if not math.isfinite(value):
        quality["nonfinite_values_by_field"][field] += 1
        row[cache_key] = None
        return None

    row[cache_key] = value
    return value


def as_bool(value):
    return (value or "").strip().lower() in {"true", "1", "yes"}


def year_of(row):
    match = re.match(r"^(\d{4})", (row.get("time") or "").strip())
    return match.group(1) if match else "unknown"


def fold_of(year):
    if not year.isdigit():
        return "other"
    if year in {"2023", "2024"}:
        return "validation_2023_2024"
    if year in {"2019", "2020", "2021", "2022"}:
        return "development_2019_2022"
    if year >= "2025":
        return "oos_2025_plus"
    return "other"


def median(values):
    return statistics.median(values) if values else None


def mean(values):
    return statistics.fmean(values) if values else None


def field_values(events, field, quality):
    return [value for event in events if (value := numeric(event, field, quality)) is not None]


def event_metrics(events, quality):
    first_plus = sum((event.get("first_hit") or "").strip() == "PLUS_1R" for event in events)
    first_minus = sum((event.get("first_hit") or "").strip() == "MINUS_1R" for event in events)
    resolved = first_plus + first_minus

    result = {
        "events": len(events),
        "resolved_events": resolved,
        "first_plus_1r": first_plus,
        "first_minus_1r": first_minus,
        "plus_1r_first_rate": first_plus / resolved if resolved else None,
        "median_mfe_r": median(field_values(events, "mfe_r", quality)),
        "median_mae_r": median(field_values(events, "mae_r", quality)),
        "sample_adequacy": {
            "minimum_events": MIN_EVENTS_FOR_INTERPRETATION,
            "minimum_resolved_events": MIN_RESOLVED_EVENTS_FOR_INTERPRETATION,
            "interpretation_allowed": len(events) >= MIN_EVENTS_FOR_INTERPRETATION and resolved >= MIN_RESOLVED_EVENTS_FOR_INTERPRETATION,
        },
    }
    for bars in (6, 12, 24, 48):
        values = field_values(events, f"return_{bars}", quality)
        result[f"mean_return_{bars}_r"] = mean(values)
        result[f"median_return_{bars}_r"] = median(values)
    return result


def fixed_rank_bucket(value):
    if value is None:
        return None
    if value < 20.0:
        return "low_lt_20"
    if value < 80.0:
        return "normal_20_80"
    return "high_ge_80"


def z_bucket(value):
    if value is None:
        return None
    if value < 1.0:
        return "inside_1sigma"
    if value < 2.0:
        return "between_1_2sigma"
    return "outside_2sigma"


def dimensions_for_shadow_row(row):
    return (
        ("return_std_rank", fixed_rank_bucket(row.get("__stddev_numeric_entry_return_std_rank"))),
        ("std_ratio_20_100", ratio_bucket_from_value(row, "entry_std_ratio_20_100")),
        ("price_abs_z20", z_bucket(row.get("__stddev_numeric_entry_price_abs_z20"))),
        ("rsi_std_rank", fixed_rank_bucket(row.get("__stddev_numeric_entry_rsi_std_rank"))),
        ("atr_return_std_ratio", fixed_rank_bucket(row.get("__stddev_numeric_entry_atr_return_std_rank"))),
    )


def ratio_bucket_from_value(row, field):
    value = row.get(f"__stddev_numeric_{field}")
    if value is None:
        return None
    if value < 0.80:
        return "compression_lt_0p80"
    if value <= 1.25:
        return "normal_0p80_1p25"
    return "expansion_gt_1p25"


def dimensions_for_pyramid_row(row):
    return (
        ("price_abs_z20", z_bucket(row.get("__stddev_numeric_add_entry_abs_z20"))),
        ("return_std_rank", fixed_rank_bucket(row.get("__stddev_numeric_add_return_std_rank"))),
        ("atr_return_std_ratio", fixed_rank_bucket(row.get("__stddev_numeric_add_atr_return_std_rank"))),
    )


def group_rows(rows, period_key, quality, dimension_builder, missing):
    groups = defaultdict(list)
    for row in rows:
        year = year_of(row)
        period = year if period_key == "year" else fold_of(year) if period_key == "fold" else "ALL"
        side = (row.get("side") or "").strip().upper()
        if side not in {"LONG", "SHORT"}:
            continue
        for dimension, bucket in dimension_builder(row):
            if bucket is None:
                missing[dimension] += 1
                continue
            groups[(period, side, dimension, bucket)].append(row)

    result = []
    for (period, side, dimension, bucket), events in sorted(groups.items()):
        result.append(
            {
                period_key: period,
                "side": side,
                "dimension": dimension,
                "bucket": bucket,
                **event_metrics(events, quality),
            }
        )
    return result


def audit_range_checks(rows, quality):
    for row in rows:
        # Parse toàn bộ cột audit để quality report không bỏ sót giá trị rỗng.
        for field in SHADOW_FIELDS:
            numeric(row, field, quality)
        for field in NON_NEGATIVE_FIELDS:
            value = numeric(row, field, quality)
            if value is not None and value < 0.0:
                quality["negative_stddev_by_field"][field] += 1
        for field in RANK_FIELDS:
            value = numeric(row, field, quality)
            if value is not None and not 0.0 <= value <= 100.0:
                quality["rank_out_of_range_by_field"][field] += 1
        abs_z = numeric(row, "entry_price_abs_z20", quality)
        if abs_z is not None and abs_z < 0.0:
            quality["negative_abs_z_events"] += 1


def counter_dict(values):
    return dict(sorted(values.items()))


def read_build_failures(journal_path):
    if journal_path is None or not journal_path.exists():
        return None
    pattern = re.compile(r"DIAG_SUMMARY stdDevShadow.*?buildFail=(\d+)")
    latest = None
    for line in read_text_auto(journal_path).splitlines():
        match = pattern.search(line)
        if match:
            latest = int(match.group(1))
    return latest


def build_pyramid_summary(paths):
    if not paths:
        return {"available": False, "files": [], "completed_events": 0, "yearly_groups": [], "fold_groups": []}

    rows = []
    fields = set()
    for path in paths:
        parsed, names = parse_csv(path)
        fields.update(names)
        rows.extend(parsed)

    quality = new_quality()
    quality["schema_missing_fields"] = sorted(set(PYRAMID_FIELDS) - fields)
    for row in rows:
        # Giữ missing/invalid của context Add1 minh bạch trong quality report.
        for field in PYRAMID_FIELDS:
            numeric(row, field, quality)
        for field in ("add_return_std_rank", "add_atr_return_std_rank"):
            value = numeric(row, field, quality)
            if value is not None and not 0.0 <= value <= 100.0:
                quality["rank_out_of_range_by_field"][field] += 1
    completed = [row for row in rows if as_bool(row.get("completed"))]
    missing = Counter()
    builder = dimensions_for_pyramid_row
    yearly = group_rows(completed, "year", quality, builder, missing)
    folds = group_rows(completed, "fold", quality, builder, missing)
    quality_payload = {
        "rows": len(rows),
        "completed_events": len(completed),
        "incomplete_events": len(rows) - len(completed),
        "schema_missing_fields": quality["schema_missing_fields"],
        "missing_values_by_field": counter_dict(quality["missing_values_by_field"]),
        "invalid_numeric_by_field": counter_dict(quality["invalid_numeric_by_field"]),
        "nonfinite_values_by_field": counter_dict(quality["nonfinite_values_by_field"]),
        "rank_out_of_range_by_field": counter_dict(quality["rank_out_of_range_by_field"]),
        "missing_bucket_values_by_dimension": counter_dict(missing),
    }
    return {
        "available": True,
        "files": [str(path) for path in paths],
        "completed_events": len(completed),
        "quality": quality_payload,
        "rank_definition": {
            "field": "add_atr_return_std_rank",
            "method": "ea_historical_percentile_rank",
            "scope": "480 closed historical observations before each Add1 event",
            "current_observation_excluded": True,
        },
        "yearly_groups": yearly,
        "fold_groups": folds,
    }


def build_summary(rows, fieldnames, pyramid_paths=None, journal_path=None):
    quality = new_quality()
    quality["schema_missing_fields"] = sorted(set(SHADOW_FIELDS) - set(fieldnames))
    audit_range_checks(rows, quality)

    completed = [row for row in rows if as_bool(row.get("completed"))]
    flat_completed = [row for row in completed if (row.get("conflict_type") or "").startswith("FLAT_")]
    missing = Counter()
    builder = dimensions_for_shadow_row
    yearly = group_rows(flat_completed, "year", quality, builder, missing)
    folds = group_rows(flat_completed, "fold", quality, builder, missing)
    all_groups = group_rows(flat_completed, "all", quality, builder, missing)

    quality_payload = {
        "rows": len(rows),
        "completed_events": len(completed),
        "flat_completed_events": len(flat_completed),
        "incomplete_events": len(rows) - len(completed),
        "non_flat_completed_events": len(completed) - len(flat_completed),
        "schema_missing_fields": quality["schema_missing_fields"],
        "missing_values_by_field": counter_dict(quality["missing_values_by_field"]),
        "invalid_numeric_by_field": counter_dict(quality["invalid_numeric_by_field"]),
        "nonfinite_values_by_field": counter_dict(quality["nonfinite_values_by_field"]),
        "negative_stddev_by_field": counter_dict(quality["negative_stddev_by_field"]),
        "rank_out_of_range_by_field": counter_dict(quality["rank_out_of_range_by_field"]),
        "negative_abs_z_events": quality["negative_abs_z_events"],
        "missing_bucket_values_by_dimension": counter_dict(missing),
        "build_failures_from_journal": read_build_failures(journal_path),
        "all_numeric_values_finite": not any(quality["nonfinite_values_by_field"].values()),
    }

    h1_yearly = [group for group in yearly if group["dimension"] == "atr_return_std_ratio"]
    h1_folds = [group for group in folds if group["dimension"] == "atr_return_std_ratio"]
    h2_yearly = [group for group in yearly if group["dimension"] == "price_abs_z20"]
    h2_folds = [group for group in folds if group["dimension"] == "price_abs_z20"]
    rsi_yearly = [group for group in yearly if group["dimension"] == "rsi_std_rank"]
    rsi_folds = [group for group in folds if group["dimension"] == "rsi_std_rank"]

    pyramid = build_pyramid_summary(pyramid_paths or [])
    return {
        "schema": {
            "required_shadow_fields": list(SHADOW_FIELDS),
            "required_pyramid_fields": list(PYRAMID_FIELDS),
            "closed_bar_contract": "EA features use closed-bar shift 1 and historical observations only; forward returns are outcome fields.",
            "price_std_pct_units": "percentage points: StdDev(Close,20) / SMA(Close,20) * 100",
            "return_std_definition": "population standard deviation of ln(Close[t] / Close[t+1]) over closed bars",
            "atr_return_std_rank_definition": "EA historical percentile rank over 480 prior closed observations; current observation excluded",
        },
        "bucket_definitions": {
            "return_std_rank": ["low_lt_20", "normal_20_80", "high_ge_80"],
            "std_ratio_20_100": ["compression_lt_0p80", "normal_0p80_1p25", "expansion_gt_1p25"],
            "price_abs_z20": ["inside_1sigma", "between_1_2sigma", "outside_2sigma"],
            "rsi_std_rank": ["low_lt_20", "normal_20_80", "high_ge_80"],
            "atr_return_std_ratio": ["low_lt_20", "normal_20_80", "high_ge_80"],
        },
        "quantiles": {
            "atr_return_std_ratio": {
                "field": "entry_atr_return_std_rank",
                "method": "ea_historical_percentile_rank",
                "scope": "480 closed historical observations before each event",
                "current_observation_excluded": True,
            }
        },
        "anti_overfitting_protocol": {
            "thresholds_preregistered": True,
            "optimizer_used": False,
            "outcomes_used_to_define_buckets": False,
            "oos_distribution_used_to_define_buckets": False,
            "execution_gate_enabled": False,
            "minimum_events_for_interpretation": MIN_EVENTS_FOR_INTERPRETATION,
            "minimum_resolved_events_for_interpretation": MIN_RESOLVED_EVENTS_FOR_INTERPRETATION,
            "slices": ["year", "fold", "LONG", "SHORT"],
            "decision_rule": "Descriptive audit only; no threshold or execution change is accepted from this report.",
        },
        "quality": quality_payload,
        "yearly_groups": yearly,
        "fold_groups": folds,
        "all_groups": all_groups,
        "hypotheses": {
            "h1_noise_regime": {
                "description": "ATR/ReturnStdDev ratio cao có thể đại diện cho range/wick nhiều nhưng displacement thấp.",
                "yearly_groups": h1_yearly,
                "fold_groups": h1_folds,
                "analysis_scope": "completed FLAT_* events, always split LONG and SHORT",
            },
            "h2_price_extension": {
                "description": "Add1 tại +2.25R khi abs Z20 > 2 có thể kém hơn khi giá chưa quá extended.",
                "base_signal_yearly_groups": h2_yearly,
                "base_signal_fold_groups": h2_folds,
                "pyramid_add1": pyramid,
                "analysis_scope": "base signals use price_abs_z20; pyramid context is included only when a pyramid CSV is supplied",
            },
            "rsi_compression_expansion": {
                "description": "RSI StdDev rank thấp/cao đại diện cho compression/expansion của RSI.",
                "yearly_groups": rsi_yearly,
                "fold_groups": rsi_folds,
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", type=Path, nargs="+", help="Một hoặc nhiều shadow-signals.csv")
    parser.add_argument(
        "--pyramid-csv",
        type=Path,
        action="append",
        default=[],
        help="CSV pyramid shadow tùy chọn để phân tích H2 Add1",
    )
    parser.add_argument("--journal", type=Path, help="Journal tùy chọn để đọc DIAG_SUMMARY stdDevShadow")
    parser.add_argument("--output", type=Path, help="Đường dẫn JSON đầu ra; mặc định in terminal")
    args = parser.parse_args()

    rows = []
    fieldnames = set()
    for path in args.csv_paths:
        parsed, names = parse_csv(path)
        rows.extend(parsed)
        fieldnames.update(names)

    result = build_summary(rows, sorted(fieldnames), args.pyramid_csv, args.journal)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
