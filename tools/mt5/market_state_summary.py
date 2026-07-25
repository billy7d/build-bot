#!/usr/bin/env python3
"""Tóm tắt trạng thái thị trường của core shadow signals có thể mở base trade."""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def as_float(value: str):
    value = value.strip()
    return float(value) if value else None


def median(values):
    return statistics.median(values) if values else None


def mean(values):
    return statistics.fmean(values) if values else None


def parse_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return list(csv.DictReader(handle, dialect=dialect))


def efficiency_bucket(row):
    value = as_float(row.get("entry_efficiency_20", ""))
    if value is None:
        return None
    if value < 0.25:
        return "low_lt_0p25"
    if value < 0.50:
        return "mid_0p25_0p50"
    return "high_ge_0p50"


def atr_rank_bucket(row):
    value = as_float(row.get("entry_atr_rank", ""))
    if value is None:
        return None
    if value < 20.0:
        return "low_lt_20"
    if value < 80.0:
        return "normal_20_80"
    return "high_ge_80"


def spread_r_bucket(row):
    value = as_float(row.get("entry_spread_r", ""))
    if value is None:
        return None
    if value <= 0.03:
        return "low_le_0p03"
    if value <= 0.10:
        return "normal_0p03_0p10"
    return "high_gt_0p10"


def sl_atr_bucket(row):
    value = as_float(row.get("initial_sl_atr", ""))
    if value is None:
        return None
    if value <= 1.0:
        return "tight_le_1"
    if value <= 2.0:
        return "normal_1_2"
    return "wide_gt_2"


def fold(year: str) -> str:
    if year in {"2023", "2024"}:
        return "validation_2023_2024"
    if year >= "2025":
        return "oos_2025_plus"
    return "other"


def metrics(events):
    first_plus = sum(event.get("first_hit") == "PLUS_1R" for event in events)
    first_minus = sum(event.get("first_hit") == "MINUS_1R" for event in events)
    resolved = first_plus + first_minus

    def values(field):
        return [value for event in events if (value := as_float(event.get(field, ""))) is not None]

    return {
        "events": len(events),
        "first_plus_1r": first_plus,
        "first_minus_1r": first_minus,
        "plus_1r_first_rate": first_plus / resolved if resolved else None,
        "median_mfe_r": median(values("mfe_r")),
        "median_mae_r": median(values("mae_r")),
        "mean_return_48_r": mean(values("return_48")),
        "median_return_48_r": median(values("return_48")),
    }


def build_summary(rows):
    complete_flat = []
    incomplete = 0
    for row in rows:
        if not as_bool(row.get("completed", "")):
            incomplete += 1
            continue
        if not row.get("conflict_type", "").startswith("FLAT_"):
            continue
        complete_flat.append(row)

    dimensions = {
        "efficiency_20": efficiency_bucket,
        "atr_rank": atr_rank_bucket,
        "spread_r": spread_r_bucket,
        "initial_sl_atr": sl_atr_bucket,
    }
    yearly = defaultdict(list)
    aggregate = defaultdict(list)
    missing = defaultdict(int)

    for row in complete_flat:
        year = row.get("time", "")[:4] or "unknown"
        side = row.get("side", "")
        for dimension, bucket_fn in dimensions.items():
            bucket = bucket_fn(row)
            if bucket is None:
                missing[dimension] += 1
                continue
            yearly[(year, side, dimension, bucket)].append(row)
            aggregate[(fold(year), side, dimension, bucket)].append(row)

    def render(groups, period_key):
        return [
            {period_key: period, "side": side, "dimension": dimension, "bucket": bucket, **metrics(events)}
            for (period, side, dimension, bucket), events in sorted(groups.items())
        ]

    return {
        "flat_completed_events": len(complete_flat),
        "incomplete_events_excluded": incomplete,
        "missing_feature_events": dict(sorted(missing.items())),
        "yearly_groups": render(yearly, "year"),
        "aggregate_groups": render(aggregate, "fold"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", type=Path, nargs="+", help="Một hoặc nhiều shadow-signals.csv")
    parser.add_argument("--output", type=Path, help="Đường dẫn JSON đầu ra; mặc định in terminal")
    args = parser.parse_args()

    rows = []
    for csv_path in args.csv_paths:
        rows.extend(parse_rows(csv_path))
    encoded = json.dumps(build_summary(rows), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
