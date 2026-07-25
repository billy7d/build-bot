#!/usr/bin/env python3
"""Tóm tắt CSV shadow-signal của Mentor_RSI_MTF_v1 theo năm, chiều và xung đột."""

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


def build_summary(rows):
    buckets = defaultdict(list)
    incomplete = 0
    for row in rows:
        if not as_bool(row.get("completed", "")):
            incomplete += 1
            continue
        year = row.get("time", "")[:4] or "unknown"
        buckets[(year, row.get("side", ""), row.get("conflict_type", ""))].append(row)

    summary = []
    for (year, side, conflict), events in sorted(buckets.items()):
        first_plus = sum(event.get("first_hit") == "PLUS_1R" for event in events)
        first_minus = sum(event.get("first_hit") == "MINUS_1R" for event in events)
        resolved = first_plus + first_minus

        def values(field):
            return [value for event in events if (value := as_float(event.get(field, ""))) is not None]

        summary.append(
            {
                "year": year,
                "side": side,
                "conflict_type": conflict,
                "events": len(events),
                "first_plus_1r": first_plus,
                "first_minus_1r": first_minus,
                "plus_1r_first_rate": first_plus / resolved if resolved else None,
                "median_mfe_r": median(values("mfe_r")),
                "median_mae_r": median(values("mae_r")),
                "mean_return_6_r": mean(values("return_6")),
                "median_return_6_r": median(values("return_6")),
                "mean_return_12_r": mean(values("return_12")),
                "median_return_12_r": median(values("return_12")),
                "mean_return_24_r": mean(values("return_24")),
                "median_return_24_r": median(values("return_24")),
                "mean_return_48_r": mean(values("return_48")),
                "median_return_48_r": median(values("return_48")),
            }
        )
    return {"completed_groups": summary, "incomplete_events_excluded": incomplete}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", type=Path, nargs="+", help="Một hoặc nhiều file Mentor_RSI_MTF_shadow_signals.csv")
    parser.add_argument("--output", type=Path, help="Đường dẫn JSON đầu ra; mặc định in ra terminal")
    args = parser.parse_args()

    rows = []
    for csv_path in args.csv_paths:
        rows.extend(parse_rows(csv_path))
    result = build_summary(rows)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
