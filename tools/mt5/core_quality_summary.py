#!/usr/bin/env python3
"""Phân tích chất lượng entry RSI từ CSV shadow, chỉ dùng signal xuất hiện khi tài khoản flat."""

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


def ema_gap_bucket(row):
    gap = abs(float(row["entry_rsi"]) - float(row["entry_ema"]))
    if gap < 1.0:
        return "gap_0_1"
    if gap < 3.0:
        return "gap_1_3"
    return "gap_3_plus"


def wma_position_bucket(row):
    side = row["side"]
    rsi = float(row["entry_rsi"])
    wma = float(row["entry_wma"])
    if side == "LONG":
        return "above_wma" if rsi > wma else "below_wma"
    return "below_wma" if rsi < wma else "above_wma"


def entry_level_bucket(row):
    rsi = float(row["entry_rsi"])
    if rsi < 45.0:
        return "below_45"
    if rsi <= 55.0:
        return "mid_45_55"
    return "above_55"


def regime_bucket(row):
    score = int(float(row["composite_regime_score"]))
    if score >= 4:
        return "bullish"
    if score <= -4:
        return "bearish"
    return "neutral"


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
        "mean_return_6_r": mean(values("return_6")),
        "mean_return_12_r": mean(values("return_12")),
        "mean_return_24_r": mean(values("return_24")),
        "mean_return_48_r": mean(values("return_48")),
        "median_return_48_r": median(values("return_48")),
    }


def build_summary(rows):
    complete_flat = [
        row
        for row in rows
        if as_bool(row.get("completed", "")) and row.get("conflict_type", "").startswith("FLAT_")
    ]
    dimensions = {
        "ema_gap": ema_gap_bucket,
        "wma_position": wma_position_bucket,
        "entry_level": entry_level_bucket,
        "regime": regime_bucket,
    }
    output = {"flat_completed_events": len(complete_flat), "dimensions": {}}
    for name, bucket_fn in dimensions.items():
        buckets = defaultdict(list)
        for row in complete_flat:
            year = row.get("time", "")[:4] or "unknown"
            buckets[(year, row.get("side", ""), bucket_fn(row))].append(row)
        output["dimensions"][name] = [
            {"year": year, "side": side, "bucket": bucket, **metrics(events)}
            for (year, side, bucket), events in sorted(buckets.items())
        ]
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", type=Path, nargs="+", help="Một hoặc nhiều shadow-signals.csv")
    parser.add_argument("--output", type=Path, help="Đường dẫn JSON đầu ra; mặc định in ra terminal")
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
