#!/usr/bin/env python3

"""Evaluate frozen V26/V63 forward samples against the approved decision gates."""

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


EXIT_PASS = 0
EXIT_WAIT = 2
EXIT_FAIL = 3


def number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def dd_percent(summary):
    value = str(summary.get("equity_drawdown_relative", ""))
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*%", value)
    return number(match.group(1)) if match else 0.0


def parse_date(value):
    for fmt in ("%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Ngày không hợp lệ: {value!r}; dùng YYYY-MM-DD")


def sample_days(summary, start_override=None, end_override=None):
    if start_override or end_override:
        if not start_override or not end_override:
            raise ValueError("Phải truyền đồng thời --start-date và --end-date")
        start = parse_date(start_override)
        end = parse_date(end_override)
        if end < start:
            raise ValueError("Ngày kết thúc đứng trước ngày bắt đầu")
        return (end - start).days + 1

    match = re.search(
        r"(\d{4}\.\d{2}\.\d{2})\s*-\s*(\d{4}\.\d{2}\.\d{2})",
        str(summary.get("period", "")),
    )
    if not match:
        raise ValueError(f"Không đọc được khoảng ngày từ Period={summary.get('period', '')!r}")
    start = datetime.strptime(match.group(1), "%Y.%m.%d").date()
    end = datetime.strptime(match.group(2), "%Y.%m.%d").date()
    if end < start:
        raise ValueError("Ngày kết thúc đứng trước ngày bắt đầu")
    return (end - start).days + 1


def load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_telemetry(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass
class Evaluation:
    command: str
    status: str = "PASS"
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    observations: dict = field(default_factory=dict)

    def fail(self, text):
        self.failures.append(text)
        self.status = "FAIL"

    def wait(self, text):
        self.warnings.append(text)
        if self.status != "FAIL":
            self.status = "WAIT"

    @property
    def exit_code(self):
        if self.status == "FAIL":
            return EXIT_FAIL
        if self.status == "WAIT":
            return EXIT_WAIT
        return EXIT_PASS

    def as_dict(self):
        return {
            "command": self.command,
            "status": self.status,
            "failures": self.failures,
            "warnings": self.warnings,
            "observations": self.observations,
        }


def telemetry_analysis(rows):
    events = Counter(row.get("event", "").strip() for row in rows)
    fills = [row for row in rows if row.get("event") in ("BASE_FILL", "PYRAMID_FILL")]
    cost_risk_money = 0.0
    risk_violations = []
    max_telemetry_dd = 0.0
    spread_r_values = []
    slippage_r_values = []

    for row in rows:
        max_telemetry_dd = max(max_telemetry_dd, number(row.get("equity_dd_pct")))
        if row.get("event") not in ("BASE_FILL", "PYRAMID_FILL"):
            continue
        desired = number(row.get("desired_risk_money"))
        actual = number(row.get("actual_risk_money"))
        if desired > 0.0 and actual > desired + max(0.01, desired * 0.001):
            risk_violations.append(
                {
                    "time": row.get("time", ""),
                    "event": row.get("event", ""),
                    "desired": desired,
                    "actual": actual,
                }
            )
        spread_r = max(0.0, number(row.get("spread_r")))
        slippage_r = abs(number(row.get("slippage_r")))
        spread_r_values.append(spread_r)
        slippage_r_values.append(slippage_r)
        cost_risk_money += actual * (spread_r + slippage_r)

    def percentile(values, pct):
        if not values:
            return 0.0
        ordered = sorted(values)
        index = math.ceil((pct / 100.0) * len(ordered)) - 1
        return ordered[max(0, min(index, len(ordered) - 1))]

    return {
        "events": dict(events),
        "fills": len(fills),
        "base_fills": events.get("BASE_FILL", 0),
        "measured_cost_money": cost_risk_money,
        "extra_half_cost_money": cost_risk_money * 0.5,
        "spread_r_median": statistics.median(spread_r_values) if spread_r_values else 0.0,
        "spread_r_p95": percentile(spread_r_values, 95),
        "slippage_r_median": statistics.median(slippage_r_values) if slippage_r_values else 0.0,
        "slippage_r_p95": percentile(slippage_r_values, 95),
        "risk_violations": risk_violations,
        "max_equity_dd_pct": max_telemetry_dd,
    }


def journal_count(journal, key):
    values = [int(value) for value in re.findall(rf"\b{re.escape(key)}=(\d+)", journal)]
    return max(values, default=0)


def evaluate_gate(args):
    summary = load_json(args.summary)
    rows = load_telemetry(args.telemetry)
    journal = args.journal.read_text(encoding="utf-8", errors="replace")
    telemetry = telemetry_analysis(rows)
    result = Evaluation(command=f"gate:{args.stage}")

    days = sample_days(summary, args.start_date, args.end_date)
    cycles = int(summary.get("closed_cycles", 0))
    pf = number(summary.get("profit_factor"))
    expectancy = number(summary.get("expected_payoff"))
    dd = dd_percent(summary)
    largest = number(summary.get("largest_profit_contribution_pct"))
    top3 = number(summary.get("top3_profit_cycles_contribution_pct"))
    stressed_net = number(summary.get("total_net_profit")) - telemetry["extra_half_cost_money"]

    result.observations = {
        "stage": args.stage,
        "sample_days": days,
        "closed_cycles": cycles,
        "profit_factor": pf,
        "expected_payoff": expectancy,
        "equity_dd_pct": dd,
        "largest_profit_gross_pct": largest,
        "top3_profit_gross_pct": top3,
        "telemetry": telemetry,
        "net_after_1_5x_measured_cost": stressed_net,
    }

    # Operational stop conditions apply immediately, even before sample maturity.
    if not rows:
        result.fail("Telemetry trống; không thể xác nhận tính đầy đủ của mẫu forward")
    if telemetry["events"].get("INIT", 0) == 0:
        result.fail("Telemetry không có sự kiện INIT")
    if telemetry["max_equity_dd_pct"] >= 8.0 or dd >= 8.0:
        result.fail(f"DD đã chạm ngưỡng pause 8% (report={dd:.2f}%, telemetry={telemetry['max_equity_dd_pct']:.2f}%)")
    if telemetry["events"].get("POST_FILL_VIOLATION", 0) > 0 or journal_count(journal, "postFillViolation") > 0:
        result.fail("Có post-fill stop/risk violation")
    if telemetry["events"].get("STOP_MODIFY_FAIL", 0) > 0 or journal_count(journal, "stopModifyFail") > 0:
        result.fail("Có lỗi sửa stop")
    if telemetry["risk_violations"]:
        result.fail(f"Actual risk vượt planned risk ở {len(telemetry['risk_violations'])} fill")
    if telemetry["events"].get("ACTUAL_RISK_VIOLATION", 0) > 0:
        result.fail(f"Có {telemetry['events']['ACTUAL_RISK_VIOLATION']} cảnh báo actual risk sau fill")
    if telemetry["events"].get("MISSING_STATE", 0) > 0:
        result.fail(f"Thiếu state/data ở {telemetry['events']['MISSING_STATE']} entry bar")
    if re.search(r"initialization failed|test failed", journal, flags=re.IGNORECASE):
        result.fail("Journal có initialization/test failure")

    disconnects = telemetry["events"].get("DISCONNECT", 0)
    reconnects = telemetry["events"].get("RECONNECT", 0)
    if disconnects > reconnects:
        result.fail(f"Có disconnect chưa phục hồi ({disconnects} disconnect, {reconnects} reconnect)")
    elif disconnects:
        result.warnings.append(f"Đã có {disconnects} disconnect và {reconnects} reconnect; kiểm tra khoảng dữ liệu")
    if telemetry["events"].get("ORDER_REJECT", 0):
        result.warnings.append(f"Có {telemetry['events']['ORDER_REJECT']} order reject; cần phân loại retcode")
    if telemetry["events"].get("RISK_REJECT", 0):
        result.warnings.append(f"Có {telemetry['events']['RISK_REJECT']} risk reject/raw-lot; kiểm tra min-lot")

    min_days, min_cycles = (90, 60) if args.stage == "stage1" else (180, 120)
    mature = days >= min_days and cycles >= min_cycles
    if not mature:
        result.wait(
            f"Mẫu chưa đủ điều kiện đến sau: {days}/{min_days} ngày và {cycles}/{min_cycles} base trades"
        )
        return result

    if pf < (1.10 if args.stage == "micro" else 0.95):
        threshold = 1.10 if args.stage == "micro" else 0.95
        result.fail(f"PF {pf:.2f} thấp hơn ngưỡng {threshold:.2f}")

    if args.stage == "micro":
        if expectancy <= 0.0:
            result.fail(f"Expected payoff không dương ({expectancy:.2f})")
        if largest >= 5.0:
            result.fail(f"Largest-profit/gross {largest:.2f}% không dưới 5%")
        if top3 > 12.0:
            result.fail(f"Top-3/gross {top3:.2f}% vượt 12%")
        if telemetry["fills"] == 0:
            result.fail("Không có fill telemetry để stress chi phí")
        elif stressed_net <= 0.0:
            result.fail(f"Net sau stress chi phí 1.5x không dương ({stressed_net:.2f})")

    return result


def evaluate_compare(args):
    baseline = load_json(args.baseline)
    candidate = load_json(args.candidate)
    result = Evaluation(command="compare:V63_vs_V26")

    base_pf = number(baseline.get("profit_factor"))
    candidate_pf = number(candidate.get("profit_factor"))
    base_dd = dd_percent(baseline)
    candidate_dd = dd_percent(candidate)
    base_cycles = int(baseline.get("closed_cycles", 0))
    candidate_cycles = int(candidate.get("closed_cycles", 0))
    long_pf = number(candidate.get("long_pf_by_deals"))
    short_pf = number(candidate.get("short_pf_by_deals"))
    required_cycles = max(args.min_cycles, math.ceil(base_cycles * 0.80))

    result.observations = {
        "baseline_pf": base_pf,
        "candidate_pf": candidate_pf,
        "pf_advantage": candidate_pf - base_pf,
        "baseline_dd_pct": base_dd,
        "candidate_dd_pct": candidate_dd,
        "baseline_cycles": base_cycles,
        "candidate_cycles": candidate_cycles,
        "required_candidate_cycles": required_cycles,
        "candidate_long_pf": long_pf,
        "candidate_short_pf": short_pf,
    }

    if baseline.get("symbol") != candidate.get("symbol"):
        result.fail("Baseline và challenger không cùng symbol")
    if base_cycles < args.min_cycles or candidate_cycles < required_cycles:
        result.wait(
            f"Chưa đủ mẫu thay baseline: V26={base_cycles}/{args.min_cycles}, "
            f"V63={candidate_cycles}/{required_cycles} cycles"
        )
        return result
    if candidate_pf < base_pf + 0.10:
        result.fail(f"V63 chỉ hơn PF {candidate_pf - base_pf:.2f}; yêu cầu ít nhất 0.10")
    if candidate_dd > base_dd + 1.0:
        result.fail(f"DD V63 cao hơn V26 {candidate_dd - base_dd:.2f} điểm %, vượt 1 điểm %")
    if long_pf < 1.0 or short_pf < 1.0:
        result.fail(f"PF hai chiều chưa đạt 1.0 (Long={long_pf:.2f}, Short={short_pf:.2f})")
    if candidate_cycles < math.ceil(base_cycles * 0.80):
        result.fail("Số trades V63 dưới 80% V26")
    return result


def render(result, as_json):
    if as_json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return
    print(f"FORWARD_GATE {result.status} command={result.command}")
    for key, value in result.observations.items():
        if key == "telemetry":
            print(
                "  telemetry: "
                f"base_fills={value['base_fills']} "
                f"spreadR[p50={value['spread_r_median']:.4f},p95={value['spread_r_p95']:.4f}] "
                f"slippageR[p50={value['slippage_r_median']:.4f},p95={value['slippage_r_p95']:.4f}] "
                f"events={value['events']}"
            )
            continue
        print(f"  {key}: {value}")
    for text in result.failures:
        print(f"  FAIL: {text}")
    for text in result.warnings:
        print(f"  WARN: {text}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    gate = subparsers.add_parser("gate", help="Đánh giá stage1, stage2 hoặc micro-live")
    gate.add_argument("--stage", choices=("stage1", "stage2", "micro"), required=True)
    gate.add_argument("--summary", type=Path, required=True)
    gate.add_argument("--telemetry", type=Path, required=True)
    gate.add_argument("--journal", type=Path, required=True)
    gate.add_argument("--start-date", help="Ngày bắt đầu mẫu YYYY-MM-DD nếu report live không có Period")
    gate.add_argument("--end-date", help="Ngày chốt report YYYY-MM-DD nếu report live không có Period")
    gate.add_argument("--json", action="store_true")

    compare = subparsers.add_parser("compare", help="Đánh giá điều kiện V63 thay V26")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--min-cycles", type=int, default=120)
    compare.add_argument("--json", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    try:
        result = evaluate_gate(args) if args.command == "gate" else evaluate_compare(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FORWARD_GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_FAIL
    render(result, args.json)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
