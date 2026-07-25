#!/usr/bin/env python3
"""Tóm tắt CSV audit Add1 pyramid theo năm, chiều, trạng thái đủ điều kiện và gate."""

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
        key = (year, row.get("side", ""), row.get("eligible", ""), row.get("gate_reason", ""))
        buckets[key].append(row)

    groups = []
    for (year, side, eligible, gate_reason), events in sorted(buckets.items()):
        first_plus = sum(event.get("first_hit") == "PLUS_1R" for event in events)
        first_minus = sum(event.get("first_hit") == "MINUS_1R" for event in events)
        resolved = first_plus + first_minus

        def values(field):
            return [value for event in events if (value := as_float(event.get(field, ""))) is not None]

        groups.append(
            {
                "year": year,
                "side": side,
                "eligible": as_bool(eligible),
                "gate_reason": gate_reason,
                "events": len(events),
                "first_plus_1r": first_plus,
                "first_minus_1r": first_minus,
                "plus_1r_first_rate": first_plus / resolved if resolved else None,
                "median_base_r": median(values("base_r")),
                "median_locked_stop_pnl_r": median(values("locked_stop_pnl_r")),
                "median_mfe_r": median(values("mfe_r")),
                "median_mae_r": median(values("mae_r")),
                "mean_return_48_r": mean(values("return_48")),
                "median_return_48_r": median(values("return_48")),
            }
        )
    return {"completed_groups": groups, "incomplete_events_excluded": incomplete}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", type=Path, nargs="+", help="Một hoặc nhiều file Mentor_RSI_MTF_pyramid_shadow.csv")
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
