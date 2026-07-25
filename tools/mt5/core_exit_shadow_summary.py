#!/usr/bin/env python3
"""Tóm tắt audit exit RSI: continuation R dương nghĩa là giữ lệnh sẽ tốt hơn exit."""

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
    overall_buckets = defaultdict(list)
    incomplete = 0
    for row in rows:
        if not as_bool(row.get("completed", "")):
            incomplete += 1
            continue
        year = row.get("time", "")[:4] or "unknown"
        key = (year, row.get("side", ""), row.get("exit_reason", ""))
        buckets[key].append(row)
        overall_buckets[(row.get("side", ""), row.get("exit_reason", ""))].append(row)

    def summarize(year, side, reason, events):
        def values(field):
            return [value for event in events if (value := as_float(event.get(field, ""))) is not None]

        return_48 = values("return_48")
        return {
            "year": year,
            "side": side,
            "exit_reason": reason,
            "events": len(events),
            "median_r_multiple_at_signal": median(values("r_multiple_at_signal")),
            "median_continuation_mfe_r": median(values("mfe_r")),
            "median_continuation_mae_r": median(values("mae_r")),
            "mean_continuation_6_r": mean(values("return_6")),
            "mean_continuation_12_r": mean(values("return_12")),
            "mean_continuation_24_r": mean(values("return_24")),
            "mean_continuation_48_r": mean(return_48),
            "median_continuation_48_r": median(return_48),
            "continuation_positive_48_rate": (
                sum(value > 0.0 for value in return_48) / len(return_48) if return_48 else None
            ),
        }

    groups = [summarize(year, side, reason, events) for (year, side, reason), events in sorted(buckets.items())]
    overall_groups = [summarize("ALL", side, reason, events) for (side, reason), events in sorted(overall_buckets.items())]
    return {
        "completed_groups": groups,
        "overall_completed_groups": overall_groups,
        "incomplete_events_excluded": incomplete,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", type=Path, nargs="+", help="Một hoặc nhiều file Mentor_RSI_MTF_core_exit_shadow.csv")
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
